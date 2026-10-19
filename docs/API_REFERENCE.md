# API Reference

The API exposes approved foundation models behind one authenticated, rate-limited endpoint. Clients choose a model **alias** (`fast`, `balanced`, `best`), never a raw model ID; the deployment decides which model each alias uses ([BUILD_PLAN.md D5](BUILD_PLAN.md#architecture-decisions)).

Base URL: the `api_url` Terraform output, `https://<api-id>.execute-api.<region>.amazonaws.com/<stage>`. [DEPLOYMENT.md steps 11-13](DEPLOYMENT.md#11-get-an-access-token) show every call below working end to end.

🏛️ **Well-Architected:** every request is authenticated and authorised (**Security**), throttled before it costs anything (**Cost Optimization**, **Reliability**), and answered with token usage and a cost estimate (**Cost Optimization**: *attribute and monitor spend*). Errors have one consistent shape and never expose internal details (**Security**, **Operational Excellence**).

## Authentication

Every request needs **both** headers:

| Header | Value | Purpose |
|---|---|---|
| `Authorization` | `Bearer <access-token>` | **Who** is calling. A Cognito access token with the API's scope, validated by API Gateway |
| `x-api-key` | The client's API key | **Which usage plan** applies (throttle and daily quota). An API key identifies a client; it is not a credential on its own |

### Getting a token (OAuth 2.0 client credentials)

```
POST <token_url>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=<oauth_scope>&client_id=<client-id>&client_secret=<client-secret>
```

The client ID and secret can be sent as HTTP Basic authentication instead of in the body. The response is:

```json
{ "access_token": "eyJ...", "expires_in": 3600, "token_type": "Bearer" }
```

Reuse the token until it expires (60 minutes): every token issued is billed, and requesting one per API call adds latency.

`token_url` and `oauth_scope` are Terraform outputs; each client's ID, secret and API key are the `client_ids`, `client_secrets` and `api_keys` outputs.

## `POST /v1/chat`

Sends a conversation to a model and returns the reply.

### Request

```json
{
  "model": "balanced",
  "system": "You are concise.",
  "messages": [
    { "role": "user", "content": "What is a permissions boundary?" }
  ],
  "max_tokens": 512,
  "temperature": 0.2,
  "stream": false
}
```

| Field | Type | Required | Rules |
|---|---|---|---|
| `model` | string | No | An alias from `GET /v1/models`. Default: the alias marked `default` (`fast`) |
| `system` | string | No | Non-empty |
| `messages` | array | Yes | 1-50 messages. Roles alternate `user`, `assistant`, `user`, ...; the first and last are `user`. `content` is a non-empty string |
| `max_tokens` | integer | No | At least 1. Values above the server-side cap (default 1024) are reduced to the cap, not rejected. Default: the cap |
| `temperature` | number | No | 0 to 1 |
| `stream` | boolean | No | Only `false` for now; streaming arrives in phase 3 |

Any other field is rejected with `400`. The whole body may be at most 64 KB.

### Response `200`

```json
{
  "output": "A permissions boundary is ...",
  "stop_reason": "end_turn",
  "usage": { "input_tokens": 21, "output_tokens": 87 },
  "cost_estimate_usd": 0.000456,
  "model": { "alias": "balanced", "model_id": "eu.anthropic.claude-sonnet-4-6" },
  "request_id": "ff052ccf-e4c2-4abc-b680-61a62c953c7d"
}
```

| Field | Meaning |
|---|---|
| `output` | The model's reply text |
| `stop_reason` | Why the model stopped: `end_turn` (finished), `max_tokens` (hit the cap; the reply is cut off), and others reported by Bedrock |
| `usage` | Tokens billed for this request |
| `cost_estimate_usd` | `usage` multiplied by the prices configured for the alias (`price_per_mtok` in `terraform.tfvars`); `null` if no prices are configured. An estimate for attribution, not an invoice |
| `model` | The alias used and the inference profile behind it |
| `request_id` | Also returned as the `x-request-id` header, and logged. Quote it when reporting a problem |

## `GET /v1/models`

Lists the aliases this deployment offers.

```json
{
  "data": [
    { "id": "balanced", "model_id": "eu.anthropic.claude-sonnet-4-6", "default": false },
    { "id": "best", "model_id": "eu.anthropic.claude-opus-4-6-v1", "default": false },
    { "id": "fast", "model_id": "eu.anthropic.claude-haiku-4-5-20251001-v1:0", "default": true }
  ]
}
```

The `model_id` values shown are examples; they depend on the deployment's `terraform.tfvars`.

## Errors

Every error, whether raised by API Gateway or by the function, has the same shape:

```json
{ "error": { "type": "invalid_request", "message": "\"model\" must be one of: balanced, best, fast.", "request_id": "..." } }
```

Messages are safe to show to users; raw model-service errors are never passed through. Errors raised by API Gateway use its own upper-case `type` values.

| Status | `type` | Raised by | Meaning | Client action |
|---|---|---|---|---|
| 400 | `invalid_request` | Function | The body failed validation (the message says which field), or the model rejected the parameters | Fix the request; don't retry unchanged |
| 400 | `unsupported` | Function | `stream: true` (not available yet) | Send `stream: false` |
| 401 | `UNAUTHORIZED` | API Gateway | Token missing, malformed, expired or without the API's scope | Get a new token for the `oauth_scope` scope |
| 403 | `INVALID_API_KEY` | API Gateway | API key missing or unknown | Send the client's `x-api-key` |
| 404 | `not_found` | API Gateway | No such route | Check the path |
| 413 | `request_too_large` | Function | Body over 64 KB | Shorten the conversation |
| 429 | `THROTTLED` | API Gateway | Client or stage rate limit exceeded | Retry with exponential backoff |
| 429 | `QUOTA_EXCEEDED` | API Gateway | Client's daily request quota used up | Wait for the quota to reset (UTC midnight) |
| 429 | `rate_limited` | Function | The model service is throttling | Retry with exponential backoff |
| 502 | `upstream_error` | Function | The model service returned an error | Retry later |
| 503 | `model_unavailable` | Function | The alias's model can't be reached by this deployment | Try another alias; tell the operator |
| 504 | `timeout` | Function | The model didn't answer within 25 seconds | Lower `max_tokens` or use a faster alias |
| 500 | `internal_error` | Function | Unexpected failure | Retry once; report the `request_id` |

## Limits

| Limit | Default | Set by | Why |
|---|---|---|---|
| Per-client rate | 2 requests/s, burst 5 | Usage plan (`client_throttle`) | One client can't starve the others (**Reliability**) |
| Per-client daily quota | 500 requests | Usage plan (`client_throttle`) | Caps spend per client (**Cost Optimization**) |
| Whole-API rate | 5 requests/s, burst 10 | Stage throttling (`stage_throttle`) | Caps total load and spend whatever the number of clients |
| `max_tokens` | 1024 | Function (`max_tokens_cap`) | Bounds the cost of a single request and keeps replies inside the timeout |
| Request body | 64 KB | Function | Bounds input tokens per request |
| Response time | 25 s model call, 29 s overall | Function and API Gateway | API Gateway REST APIs end non-streaming requests at 29 seconds |

Variables in parentheses are in `terraform/variables.tf` and can be overridden in `terraform.tfvars`.
