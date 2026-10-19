import assert from "node:assert/strict";
import { test } from "node:test";
import { estimateCost, parseChatRequest } from "./chat";
import type { Config } from "./config";
import { ApiError, toApiError } from "./http";
import { modelCallMetrics } from "./metrics";

const config: Config = {
  models: {
    fast: { arn: "arn:fast", modelId: "geo.fast-model", inputPerMtok: 1, outputPerMtok: 5 },
    unpriced: { arn: "arn:unpriced", modelId: "geo.other", inputPerMtok: null, outputPerMtok: null },
  },
  defaultModel: "fast",
  maxTokensCap: 1024,
  maxBodyBytes: 1000,
  bedrockTimeoutMs: 25000,
  metricsNamespace: "Test",
};

const parse = (body: unknown) => parseChatRequest(JSON.stringify(body), false, config);
const hello = [{ role: "user", content: "Hello" }];

function rejects(body: unknown, status: number, type: string) {
  assert.throws(
    () => parse(body),
    (e: unknown) => e instanceof ApiError && e.status === status && e.type === type,
  );
}

test("minimal request uses the default alias and the token cap", () => {
  const req = parse({ messages: hello });
  assert.equal(req.alias, "fast");
  assert.equal(req.model.arn, "arn:fast");
  assert.equal(req.maxTokens, 1024);
  assert.deepEqual(req.messages, [{ role: "user", content: [{ text: "Hello" }] }]);
});

test("max_tokens above the cap is capped, not rejected", () => {
  assert.equal(parse({ messages: hello, max_tokens: 50_000 }).maxTokens, 1024);
  assert.equal(parse({ messages: hello, max_tokens: 10 }).maxTokens, 10);
});

test("invalid requests are rejected before any model call", () => {
  rejects({ messages: hello, model: "gpt" }, 400, "invalid_request");
  rejects({ messages: hello, model: "arn:fast" }, 400, "invalid_request");
  rejects({ messages: hello, model: "toString" }, 400, "invalid_request");
  rejects({ messages: [] }, 400, "invalid_request");
  rejects({ messages: [{ role: "assistant", content: "Hi" }] }, 400, "invalid_request");
  rejects({ messages: [{ role: "user", content: "a" }, { role: "user", content: "b" }] }, 400, "invalid_request");
  rejects({ messages: hello, temperature: 2 }, 400, "invalid_request");
  rejects({ messages: hello, max_tokens: 0 }, 400, "invalid_request");
  rejects({ messages: hello, extra: 1 }, 400, "invalid_request");
  rejects({ messages: hello, stream: true }, 400, "unsupported");
  rejects({ messages: [{ role: "user", content: "x".repeat(2000) }] }, 413, "request_too_large");
  assert.throws(() => parseChatRequest("{not json", false, config), ApiError);
  assert.throws(() => parseChatRequest(null, false, config), ApiError);
});

test("base64 bodies are decoded", () => {
  const b64 = Buffer.from(JSON.stringify({ messages: hello })).toString("base64");
  assert.equal(parseChatRequest(b64, true, config).alias, "fast");
});

test("cost estimate uses the price table", () => {
  assert.equal(estimateCost(config.models.fast!, 1_000_000, 200_000), 2);
  assert.equal(estimateCost(config.models.unpriced!, 100, 100), null);
});

test("Bedrock errors map to client-safe errors", () => {
  const named = (name: string) => Object.assign(new Error("raw detail"), { name });
  assert.equal(toApiError(named("ThrottlingException")).status, 429);
  assert.equal(toApiError(named("ValidationException")).status, 400);
  assert.equal(toApiError(named("AccessDeniedException")).status, 503);
  assert.equal(toApiError(named("TimeoutError")).status, 504);
  assert.equal(toApiError(named("Something")).message, "Internal error.");
});

test("EMF block declares exactly the metrics present", () => {
  const line = modelCallMetrics("Test", "fast", { InputTokens: 10, OutputTokens: 2, ModelLatency: 300 });
  const declared = (line._aws as any).CloudWatchMetrics[0];
  assert.deepEqual(declared.Dimensions, [["Model"]]);
  assert.deepEqual(declared.Metrics.map((m: { Name: string }) => m.Name), ["InputTokens", "OutputTokens", "ModelLatency"]);
  assert.equal(line.Model, "fast");
  assert.equal(line.InputTokens, 10);
  assert.equal("CostUSD" in line, false);
});
