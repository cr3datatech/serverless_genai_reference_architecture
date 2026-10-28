// Minimal Node.js client for the GenAI API (Node 18 or later, no dependencies).
//
// The same patterns as genai_client.py:
//
// * OAuth 2.0 client-credentials token, cached and reused until shortly
//   before it expires (every token issued is billed, and fetching one per
//   call adds latency).
// * Both headers on every call: `Authorization: Bearer <token>` (who is
//   calling) and `x-api-key` (which usage plan applies).
// * Retries with exponential backoff and jitter on 429 and 5xx
//   (Well-Architected Reliability: REL05-BP03 control and limit retry calls).
//
// Configuration comes from the same environment variables as the Python
// client: GENAI_API_URL, GENAI_TOKEN_URL, GENAI_SCOPE, GENAI_CLIENT_ID,
// GENAI_CLIENT_SECRET, GENAI_API_KEY (docs/HOW_TO.md section 1).
//
// Usage from the command line:
//
//     node examples/genai_client.mjs "Explain AWS Lambda in two sentences." balanced
//
// Usage from code:
//
//     import { ask, chat } from "./genai_client.mjs";
//     const answer = await ask("Explain AWS Lambda in two sentences.", "balanced");

const RETRYABLE_STATUS = new Set([429, 500, 502, 503, 504]);
const NAMES = ["API_URL", "TOKEN_URL", "SCOPE", "CLIENT_ID", "CLIENT_SECRET", "API_KEY"];

export class ApiError extends Error {
  constructor(status, error) {
    super(`${status} ${error.type ?? "unknown"}: ${error.message ?? ""} (request_id ${error.request_id})`);
    this.status = status;
    this.type = error.type ?? "unknown";
    this.requestId = error.request_id;
  }
}

function settings() {
  const missing = NAMES.filter((n) => !process.env[`GENAI_${n}`]).map((n) => `GENAI_${n}`);
  if (missing.length) throw new Error(`Missing environment variables: ${missing.join(", ")}`);
  return Object.fromEntries(NAMES.map((n) => [n, process.env[`GENAI_${n}`]]));
}

let token;
let tokenExpires = 0;

async function getToken(s) {
  // Renew a minute early so a token never expires mid-request.
  if (token && Date.now() < tokenExpires - 60_000) return token;
  const res = await fetch(s.TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "client_credentials",
      scope: s.SCOPE,
      client_id: s.CLIENT_ID,
      client_secret: s.CLIENT_SECRET,
    }),
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) throw new ApiError(res.status, { type: "token_error", message: await res.text() });
  const data = await res.json();
  token = data.access_token;
  tokenExpires = Date.now() + (data.expires_in ?? 3600) * 1000;
  return token;
}

// Sends one request; returns the JSON body. Throws ApiError.
export async function request(method, path, body, { maxAttempts = 4 } = {}) {
  const s = settings();
  for (let attempt = 1; ; attempt++) {
    const res = await fetch(s.API_URL + path, {
      method,
      headers: {
        authorization: `Bearer ${await getToken(s)}`,
        "x-api-key": s.API_KEY,
        "content-type": "application/json",
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(35_000),
    });
    const text = await res.text();
    let json;
    try {
      json = JSON.parse(text);
    } catch {
      json = { error: { type: "unknown", message: text } };
    }
    if (res.ok) return json;
    if (RETRYABLE_STATUS.has(res.status) && attempt < maxAttempts) {
      // Exponential backoff with full jitter: 0-1 s, 0-2 s, 0-4 s ...
      await new Promise((r) => setTimeout(r, Math.random() * 1000 * 2 ** (attempt - 1)));
      continue;
    }
    throw new ApiError(res.status, json.error ?? {});
  }
}

// Full control: pass the whole conversation and any optional fields.
export async function chat({ messages, model, system, max_tokens, temperature }) {
  const body = { messages };
  for (const [k, v] of Object.entries({ model, system, max_tokens, temperature })) {
    if (v !== undefined) body[k] = v;
  }
  return request("POST", "/v1/chat", body);
}

// One question, one answer.
export async function ask(prompt, model) {
  const r = await chat({ messages: [{ role: "user", content: prompt }], model });
  return r.output;
}

export async function models() {
  return (await request("GET", "/v1/models")).data;
}

// Command-line entry point: node examples/genai_client.mjs "question" [alias]
if (import.meta.url === `file://${process.argv[1]}` || process.argv[1]?.endsWith("genai_client.mjs")) {
  const [prompt, model] = process.argv.slice(2);
  if (!prompt) {
    console.error('Usage: node examples/genai_client.mjs "question" [alias]');
    process.exit(2);
  }
  try {
    const r = await chat({ messages: [{ role: "user", content: prompt }], model });
    console.log(r.output);
    const u = r.usage;
    console.error(`\n[${r.model.alias} | ${u.input_tokens} in / ${u.output_tokens} out tokens | ~$${r.cost_estimate_usd} | stop: ${r.stop_reason} | request ${r.request_id}]`);
  } catch (e) {
    console.error(e.message);
    process.exit(1);
  }
}
