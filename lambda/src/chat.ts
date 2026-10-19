import type { Message } from "@aws-sdk/client-bedrock-runtime";
import type { Config, ModelConfig } from "./config";
import { ApiError } from "./http";

export interface ChatRequest {
  alias: string;
  model: ModelConfig;
  system?: string;
  messages: Message[];
  maxTokens: number;
  temperature?: number;
}

const ALLOWED_FIELDS = new Set(["model", "system", "messages", "max_tokens", "temperature", "stream"]);
const MAX_MESSAGES = 50;

function invalid(message: string): ApiError {
  return new ApiError(400, "invalid_request", message);
}

/**
 * Validates the client request and resolves the model alias. Everything a
 * client can influence is checked here, before any model call is paid for
 * (Security: validate input; Cost: no spend on bad requests).
 */
export function parseChatRequest(rawBody: string | null, isBase64: boolean, config: Config): ChatRequest {
  if (!rawBody) throw invalid("Request body is required.");
  const text = isBase64 ? Buffer.from(rawBody, "base64").toString("utf8") : rawBody;
  if (Buffer.byteLength(text, "utf8") > config.maxBodyBytes) {
    throw new ApiError(413, "request_too_large", `Request body exceeds ${config.maxBodyBytes} bytes.`);
  }

  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    throw invalid("Request body is not valid JSON.");
  }
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    throw invalid("Request body must be a JSON object.");
  }
  const b = body as Record<string, unknown>;

  const unknown = Object.keys(b).filter((k) => !ALLOWED_FIELDS.has(k));
  if (unknown.length > 0) throw invalid(`Unknown field(s): ${unknown.join(", ")}.`);

  if (b.stream === true) {
    throw new ApiError(400, "unsupported", "Streaming is not available yet. Send \"stream\": false or omit it.");
  }
  if (b.stream !== undefined && b.stream !== false) throw invalid("\"stream\" must be a boolean.");

  const alias = b.model === undefined ? config.defaultModel : b.model;
  if (typeof alias !== "string" || !Object.hasOwn(config.models, alias)) {
    throw invalid(`"model" must be one of: ${Object.keys(config.models).join(", ")}.`);
  }

  if (b.system !== undefined && (typeof b.system !== "string" || b.system.length === 0)) {
    throw invalid("\"system\" must be a non-empty string.");
  }

  if (!Array.isArray(b.messages) || b.messages.length === 0 || b.messages.length > MAX_MESSAGES) {
    throw invalid(`"messages" must be an array of 1 to ${MAX_MESSAGES} messages.`);
  }
  const messages: Message[] = b.messages.map((m: unknown, i: number) => {
    const msg = m as Record<string, unknown> | null;
    if (typeof msg !== "object" || msg === null || (msg.role !== "user" && msg.role !== "assistant")) {
      throw invalid(`messages[${i}].role must be "user" or "assistant".`);
    }
    if (typeof msg.content !== "string" || msg.content.length === 0) {
      throw invalid(`messages[${i}].content must be a non-empty string.`);
    }
    const expected = i % 2 === 0 ? "user" : "assistant";
    if (msg.role !== expected) {
      throw invalid("Messages must alternate, starting with \"user\".");
    }
    return { role: msg.role, content: [{ text: msg.content }] };
  });
  if (messages[messages.length - 1]?.role !== "user") {
    throw invalid("The last message must have role \"user\".");
  }

  let maxTokens = config.maxTokensCap;
  if (b.max_tokens !== undefined) {
    if (!Number.isInteger(b.max_tokens) || (b.max_tokens as number) < 1) {
      throw invalid("\"max_tokens\" must be a positive integer.");
    }
    // Capped, not rejected: the server-side ceiling bounds cost and latency (D9).
    maxTokens = Math.min(b.max_tokens as number, config.maxTokensCap);
  }

  if (b.temperature !== undefined) {
    if (typeof b.temperature !== "number" || b.temperature < 0 || b.temperature > 1) {
      throw invalid("\"temperature\" must be a number from 0 to 1.");
    }
  }

  return {
    alias,
    model: config.models[alias]!,
    system: b.system as string | undefined,
    messages,
    maxTokens,
    temperature: b.temperature as number | undefined,
  };
}

/** Token cost from the configured price table (D7); null when no prices are set. */
export function estimateCost(model: ModelConfig, inputTokens: number, outputTokens: number): number | null {
  if (model.inputPerMtok === null || model.outputPerMtok === null) return null;
  const usd = (inputTokens * model.inputPerMtok + outputTokens * model.outputPerMtok) / 1_000_000;
  return Math.round(usd * 1_000_000) / 1_000_000;
}
