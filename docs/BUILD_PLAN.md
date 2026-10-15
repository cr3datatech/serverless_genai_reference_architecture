# Build Plan

How this reference architecture is built, in order, and the decisions behind it. Every decision names the **AWS Well-Architected Framework** pillar(s) it serves, and the finished stack is reviewed against all six pillars before release ([WELL_ARCHITECTED_REVIEW.md](WELL_ARCHITECTED_REVIEW.md)).

New to these services? Read the [Learning Guide](LEARNING_GUIDE.md) first - it explains each component and concept this plan relies on.

## Goal

The minimal, production-shaped, secure pattern for exposing a foundation model as an API on AWS:

- **Converse API** on Amazon Bedrock, streaming and non-streaming, with server-side model selection
- **Authenticated, rate-limited** REST endpoint
- **Per-request cost and token visibility**, latency metrics, tracing and alarms
- **Least privilege** throughout, every workload role capped by a permissions boundary ([bootstrap/iam](../bootstrap/iam/README.md))
- **One `terraform apply`** to deploy, one `terraform destroy` to remove, with nothing left behind

*Pillar key: OPS = Operational Excellence · SEC = Security · REL = Reliability · PERF = Performance Efficiency · COST = Cost Optimization · SUS = Sustainability. The [Learning Guide §5](LEARNING_GUIDE.md#5-every-decision-mapped-to-well-architected) shows the full matrix.*

### Out of scope (later builds)

RAG / knowledge bases · Bedrock Guardrails · VPC endpoints and customer-managed KMS keys · Bedrock model invocation logging (account-wide setting) · agents · prompt caching, model routing and evaluation. The README's feature list will be trimmed to match what this build delivers.

## Architecture decisions

| # | Decision | Choice | 🏛️ Well-Architected | Why |
|---|----------|--------|-----|-----|
| D1 | API front door | **API Gateway REST API** (regional) | REL, COST, OPS | The only API Gateway type with API keys, usage plans (per-client throttling and quotas), native X-Ray tracing and WAF support. It now also supports **response streaming** with Lambda proxy integrations, which used to require Function URLs. HTTP APIs are cheaper but have no API keys, usage plans or streaming |
| D2 | Client authentication | **Open, see below** | SEC | API keys identify and meter clients, but AWS advises against using them as the only authentication |
| D3 | Lambda runtime | **Open, see below** | PERF, OPS | Native Lambda response streaming is only available on Node.js managed runtimes |
| D4 | CPU architecture | **arm64 (Graviton)** | COST, SUS | About 20% cheaper per GB-second, and lower energy use (Cost and Sustainability pillars) |
| D5 | Model selection | **Server-side aliases** (`fast`, `balanced`, `best`) mapped to an allowlist of Bedrock inference-profile IDs in Terraform variables | COST, SEC, OPS | Clients never send raw model IDs. Models change through configuration, not code, and an unapproved or expensive model can't be requested |
| D6 | Model access | **Geographic cross-region inference profiles** matching the deployment region (e.g. `eu.`, `us.`, `apac.` prefixes) | REL, PERF, SEC | Current Claude models are reached through inference profiles in most regions. A geographic profile spreads load across regions for capacity while keeping requests inside that geography (data residency). Exact IDs are discovered at deploy time with `aws bedrock list-inference-profiles`, not hard-coded |
| D7 | Cost tracking | Token usage from the Converse response × a per-model **price table in config**, emitted as **CloudWatch Embedded Metric Format** log lines | COST, OPS | EMF needs no `PutMetricData` call and no extra permissions; metrics and logs come from the same line. Prices live in config so they're easy to update |
| D8 | Prompt and response logging | **Metadata only by default** (model, token counts, latency, cost, request ID). Content logging off, behind a variable | SEC | Privacy by default (Security pillar). Full content logging belongs to Bedrock invocation logging in the security build |
| D9 | Cost and abuse ceilings | Usage-plan throttle + quota, stage-level throttling, **Lambda reserved concurrency**, `max_tokens` cap, request size limit | COST, REL | Several independent limits on spend, so one misconfiguration can't produce a runaway bill |
| D10 | Terraform state | **S3 backend with native locking** (`use_lockfile`, Terraform ≥ 1.10), versioned and encrypted bucket `powerlab-tfstate-<suffix>`; backend settings in a gitignored `backend.hcl` | REL, SEC, OPS | No DynamoDB table needed, and no account details in the repo |
| D11 | Tagging | Provider `default_tags`: `Project=powerlab`, `Component=genai-api`, `ManagedBy=terraform` | COST, OPS | Scopes the Well-Architected review to this stack in a shared account, and enables cost allocation |
| D12 | Code layout | Flat Terraform root (one file per concern) rather than modules | OPS | Easier to read as a reference. Modules come when later builds reuse pieces |

### Open decisions

**D2: Authentication**

| Option | How it works | Trade-off |
|---|---|---|
| **A. Cognito machine-to-machine + API key** (recommended) | Clients get a JWT through the OAuth client-credentials flow; API Gateway validates it with a Cognito authorizer. The API key is still required, for usage-plan metering | The realistic pattern for internal service-to-service APIs. Requires deploy policy v2 (Cognito permissions) |
| B. IAM (SigV4) auth + API key | Clients sign requests with AWS credentials (`curl --aws-sigv4`, SDKs) | No new service and strong auth, but only clients with AWS credentials can call it |
| C. API key only | `x-api-key` header | Simplest, but the Well-Architected review would flag it. Fine for a demo only |

**D3: Lambda runtime and streaming**

| Option | How it works | Trade-off |
|---|---|---|
| **A. Node.js 22 + TypeScript** (recommended) | `awslambda.streamifyResponse` with `ConverseStreamCommand` from the AWS SDK v3 | Native streaming, no layers, fast cold starts. Python stays for the example client and test scripts |
| B. Python 3.13 + Lambda Web Adapter | A small web app (FastAPI) with the AWS Lambda Web Adapter in `response_stream` mode | Keeps everything in Python (as the current README describes), but adds a public layer or container image. Both need extra deploy permissions and move parts |

## API contract

```
POST /v1/chat
x-api-key: <key>
Authorization: Bearer <jwt>        (if D2 = A)

{
  "model": "balanced",                         // alias, default "fast"
  "system": "You are concise.",                // optional
  "messages": [{"role": "user", "content": "Hello"}],
  "max_tokens": 1024,                          // capped server-side
  "temperature": 0.2,                          // optional
  "stream": false
}
```

- **`stream: false`:** JSON response with `output`, `stop_reason`, `usage` (input/output tokens), `cost_estimate_usd`, `model` (the alias and the resolved model ID), `request_id`.
- **`stream: true`:** a chunked `text/event-stream` of `delta` events, then a final `usage` event with the same token and cost fields.
- **Errors:** consistent JSON `{error: {type, message, request_id}}`, with Bedrock throttling mapped to 429 and validation errors to 400. Raw Bedrock errors are never passed through.
- **`GET /v1/models`:** lists the aliases this deployment exposes.

## Phases

Each phase ends with something deployed and testable, and names the Well-Architected focus it adds.

| # | Phase | Delivers | 🏛️ Well-Architected focus |
|---|-------|----------|----------|
| 0 | **Prerequisites** | D2/D3 decided; deploy policy v2 applied if needed; Claude models confirmed in Bedrock in the deployment region; API Gateway account CloudWatch role checked (`aws apigateway get-account`) | Security (model access, account-wide settings understood) |
| 1 | **Terraform foundation** | State bucket, `backend.hcl` (gitignored), providers, `default_tags`, `terraform.tfvars.example`; Lambda execution role with `permissions_boundary`; inline policy limited to Bedrock invoke on the allowlisted profiles, plus logs and X-Ray | Security (boundary, least privilege), Operational Excellence (IaC, tagging) |
| 2 | **Non-streaming path** | Lambda Converse handler (validation, alias resolution, usage and cost); REST API `/v1/chat`, `/v1/models`; API key and usage plan; authorizer (D2); first end-to-end `curl` | Security (authentication), Cost (usage plans), Reliability (error mapping) |
| 3 | **Streaming path** | `ConverseStream` with response streaming through API Gateway; final usage event; timeout and disconnect handling | Performance Efficiency (time to first token), Reliability (timeouts) |
| 4 | **Observability and cost** | Structured JSON logs; X-Ray on API Gateway and Lambda; EMF metrics (tokens, cost, latency by model); access logs; dashboard; alarms (5xx rate, Lambda errors, throttles, p95 latency, daily estimated cost) to an SNS topic | Operational Excellence, Cost Optimization (visibility, alarms) |
| 5 | **Tests, examples, docs** | Unit tests (Bedrock stubbed); integration test against the deployed stage; `examples/` (Python client, curl); `ARCHITECTURE.md`, `DEPLOYMENT.md`, `API_REFERENCE.md`, `COST_ANALYSIS.md` (current Bedrock prices); README corrected to current models and features | Operational Excellence (tests, runbooks), Cost (current pricing) |
| 6 | **Well-Architected review** | Read-only six-pillar assessment of the deployed stack (scoped to `Project=powerlab`), fixes, re-assessment; sanitised results in `WELL_ARCHITECTED_REVIEW.md` | All six pillars - evidence-based review, remediation, re-review |
| 7 | **Release** | Tagged `v1.0`, architecture diagram, write-up ("the minimal secure pattern for a GenAI endpoint on AWS"), `terraform destroy` verified clean | Operational Excellence (clean teardown), Sustainability (no leftovers) |

## Deploy policy v2 (likely additions)

Kept in [bootstrap/iam](../bootstrap/iam/README.md) and applied by an administrator with `create-policy-version`.

- **SNS:** create, delete, tag and subscribe on `topic:powerlab-*` (alarm notifications)
- **Cognito** (if D2 = A): user pool, resource server, app client and domain. User pool ARNs contain generated IDs rather than names, so access is scoped by the `aws:ResourceTag/Project` condition instead of by name
- **Lambda layers** (only if D3 = B): `lambda:GetLayerVersion` on the published Lambda Web Adapter layer

## Definition of done

- `terraform apply` from a clean checkout with only `terraform.tfvars` and `backend.hcl` filled in; `terraform destroy` leaves nothing behind
- Streaming and non-streaming calls work through the public endpoint with authentication; unauthenticated, over-quota and invalid requests are rejected with the right status codes
- Every request has a trace, a structured log line and cost/token metrics; the dashboard and alarms work
- Every IAM role carries the permissions boundary; Access Analyzer reports no errors or security warnings
- The Well-Architected review is complete for all six pillars, with no open high-risk issues (HRIs) and every medium-risk issue (MRI) either fixed or recorded as an accepted risk with its reason
- The repo contains no account IDs, profile names, endpoints or personal details

## Risks

| Risk | Mitigation |
|------|------------|
| Terraform AWS provider support for REST API response streaming is new | Spike it first in phase 3. Fallback: define the integration through an OpenAPI body (`x-amazon-apigateway-integration`) |
| Claude models not enabled in the account | Check in phase 0; submitting the one-time Anthropic use-case form is an admin action |
| API Gateway account CloudWatch role not set | Check in phase 0. If unset, an admin sets it once; it's account-wide, so the deploy role can't change it |
| Shared account: account-level review findings (CloudTrail, GuardDuty, root MFA) not caused by this stack | Report them as context; only findings for this stack go in the published review |
| Bedrock price changes | Prices are in config, not code; `COST_ANALYSIS.md` records the date the prices were checked |
