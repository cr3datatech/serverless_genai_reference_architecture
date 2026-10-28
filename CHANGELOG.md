# Changelog

## Unreleased

- **F-001 remediated:** the account's Lambda concurrency limit is now the default 1000. A second Well-Architected re-assessment (A6, 2026-10-28) leaves no open workload risks ([WELL_ARCHITECTED_REVIEW.md](docs/WELL_ARCHITECTED_REVIEW.md))
- Deployment guide: every step states its prerequisites ("Before you run")
- [HOW_TO.md](docs/HOW_TO.md): calling the model from your own terminal (Python, Node.js, curl, PowerShell) and from your own code, including an AWS Lambda function pattern
- `examples/genai_client.mjs`: a dependency-free Node.js client matching the Python one

## v1.0 - 2026-10-20

First release of the serverless GenAI reference architecture: a Well-Architected gateway to foundation models on Amazon Bedrock.

### Included

- **API:** REST API with `POST /v1/chat` (non-streaming) and `GET /v1/models`; OAuth 2.0 client-credentials tokens from Amazon Cognito plus an API key per client; per-client throttle and daily quota; stage throttle; JSON errors throughout ([API_REFERENCE.md](docs/API_REFERENCE.md))
- **Models:** three aliases (`fast`, `balanced`, `best`) mapped to Claude models through tagged application inference profiles with EU geographic routing; IAM allows only the configured models
- **Cost:** token usage and `cost_estimate_usd` on every response; per-alias cost metrics; daily cost alarm; account budget ([COST_ANALYSIS.md](docs/COST_ANALYSIS.md))
- **Observability:** one metadata-only JSON log line per request with embedded metrics; X-Ray on the function; API Gateway access log; four alarms to SNS email
- **Security:** least-privilege function role under a permissions boundary; MFA-protected deploy and read-only review roles; no prompts or answers logged
- **Infrastructure as code:** Terraform for the whole stack, with pinned providers and one-time bootstrap steps for IAM, Cognito and the budget
- **Tests:** unit tests for the function and integration tests against the deployed API, including every refusal
- **Docs:** learning guide, architecture, deployment runbook, preflight checks, API reference, cost analysis, write-up, and the Well-Architected review

### Verified for this release

- `terraform destroy` removes every stack resource; only the bootstrap foundations remain (state bucket, IAM, Cognito user pool, budget)
- A fresh clone with only `terraform.tfvars` and `backend.hcl` filled in builds, tests, deploys (36 resources) and passes all integration tests; a second plan reports no changes
- IAM Access Analyzer policy validation reports no findings on any policy
- Well-Architected review (A1) and re-assessment (A6): open risks down from 0 high, 3 medium, 3 low to 0 high, 1 medium ([WELL_ARCHITECTED_REVIEW.md](docs/WELL_ARCHITECTED_REVIEW.md))

### Known limitations

- **F-001 (Reliability, medium):** the account's Lambda concurrency quota is 10; an increase to the default 1000 is requested and pending with AWS. Bounded by the API throttles and covered by the throttles alarm
- Streaming responses are not included (planned)
- The newest Claude models are restricted for the account used; the aliases map to the previous generation ([PREFLIGHT_CHECKS 6.3](docs/PREFLIGHT_CHECKS.md#63-enable-model-access))
- WAF, customer managed KMS keys, VPC endpoints, Bedrock Guardrails and invocation logging are left to the security build ([ARCHITECTURE.md](docs/ARCHITECTURE.md#known-limitations-and-trade-offs))

### Fixed during release testing

- The API redeployment trigger hashed whole gateway-response resources; AWS reads one attribute back differently after creation, so the first plan after a fresh deploy wanted to redeploy. The trigger now hashes only the response settings
