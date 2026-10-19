import { BedrockRuntimeClient, ConverseCommand } from "@aws-sdk/client-bedrock-runtime";
import type { APIGatewayProxyEvent, APIGatewayProxyResult, Context } from "aws-lambda";
import { estimateCost, parseChatRequest } from "./chat";
import { loadConfig } from "./config";
import { ApiError, errorResponse, json, toApiError } from "./http";

// Created once per execution environment and reused across invocations
// (Performance Efficiency: no per-request client setup).
const config = loadConfig();
// One retry inside the time budget; the client retries throttling with backoff.
const bedrock = new BedrockRuntimeClient({ maxAttempts: 2 });

export const handler = async (event: APIGatewayProxyEvent, context: Context): Promise<APIGatewayProxyResult> => {
  const requestId = event.requestContext?.requestId ?? context.awsRequestId;
  const started = Date.now();

  // One structured log line per request, metadata only: no prompt or response
  // text is ever logged (BUILD_PLAN.md D8, Security pillar).
  const log: Record<string, unknown> = {
    request_id: requestId,
    route: `${event.httpMethod} ${event.resource}`,
    client_id: event.requestContext?.authorizer?.claims?.client_id,
  };

  try {
    let response: APIGatewayProxyResult;
    if (event.httpMethod === "GET" && event.resource === "/v1/models") {
      response = listModels(requestId);
    } else if (event.httpMethod === "POST" && event.resource === "/v1/chat") {
      response = await chat(event, requestId, log);
    } else {
      throw new ApiError(404, "not_found", "Route not found.");
    }
    log.status = response.statusCode;
    return response;
  } catch (e) {
    const err = toApiError(e);
    log.status = err.status;
    log.error_type = err.type;
    if (!(e instanceof ApiError)) log.error_name = e instanceof Error ? e.name : String(e);
    return errorResponse(err, requestId);
  } finally {
    log.latency_ms = Date.now() - started;
    // Written raw (not via console.log) so each line is one JSON document,
    // ready for CloudWatch Logs Insights and, later, Embedded Metric Format.
    process.stdout.write(JSON.stringify(log) + "\n");
  }
};

function listModels(requestId: string): APIGatewayProxyResult {
  const data = Object.entries(config.models).map(([id, m]) => ({
    id,
    model_id: m.modelId,
    default: id === config.defaultModel,
  }));
  return json(200, { data }, requestId);
}

async function chat(
  event: APIGatewayProxyEvent,
  requestId: string,
  log: Record<string, unknown>,
): Promise<APIGatewayProxyResult> {
  const req = parseChatRequest(event.body, event.isBase64Encoded, config);
  log.model = req.alias;

  const result = await bedrock.send(
    new ConverseCommand({
      modelId: req.model.arn,
      messages: req.messages,
      system: req.system ? [{ text: req.system }] : undefined,
      inferenceConfig: { maxTokens: req.maxTokens, temperature: req.temperature },
    }),
    // Stay inside the API Gateway integration timeout (29 s) so the client
    // gets a clean 504 from us rather than a gateway timeout.
    { abortSignal: AbortSignal.timeout(config.bedrockTimeoutMs) },
  );

  const inputTokens = result.usage?.inputTokens ?? 0;
  const outputTokens = result.usage?.outputTokens ?? 0;
  const cost = estimateCost(req.model, inputTokens, outputTokens);
  Object.assign(log, {
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    cost_estimate_usd: cost,
    model_latency_ms: result.metrics?.latencyMs,
    stop_reason: result.stopReason,
  });

  const output = (result.output?.message?.content ?? []).map((c) => c.text ?? "").join("");
  return json(
    200,
    {
      output,
      stop_reason: result.stopReason,
      usage: { input_tokens: inputTokens, output_tokens: outputTokens },
      cost_estimate_usd: cost,
      model: { alias: req.alias, model_id: req.model.modelId },
      request_id: requestId,
    },
    requestId,
  );
}
