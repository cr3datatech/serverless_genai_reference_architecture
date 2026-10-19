# Serverless GenAI Reference Architecture

A production-ready template for building Generative AI APIs on AWS using managed serverless services.

## Overview

This repository provides a reusable, enterprise-grade reference architecture for deploying foundation models via REST APIs without managing servers. It combines AWS Bedrock, Lambda, API Gateway, and observability to deliver a scalable, secure, cost-conscious pattern for GenAI applications.

**Perfect for:**
- Teams building internal GenAI APIs
- Proof-of-concepts that need to scale quickly
- Organizations evaluating Bedrock costs and performance
- Learning AWS GenAI best practices (AWS Certified Generative AI Developer – Professional)

## Start Here

This repository is built to be learned from, not just deployed. Every design decision is explained and justified against the six pillars of the **AWS Well-Architected Framework** - Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization and Sustainability - and the finished stack is audited against them.

| Read | To learn |
|------|----------|
| [docs/LEARNING_GUIDE.md](docs/LEARNING_GUIDE.md) | What each AWS service does, how a request flows, why every choice was made, which Well-Architected pillar it serves, and how it maps to the AIP-C01 exam. Includes self-check questions |
| [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md) | The build order, architecture decisions (each tagged with its Well-Architected pillars), API contract and definition of done |
| [bootstrap/iam/README.md](bootstrap/iam/README.md) | Least-privilege IAM set up *before* anything is deployed: temporary credentials, MFA, permissions boundaries - the Well-Architected Security pillar in practice |
| [bootstrap/budget/README.md](bootstrap/budget/README.md) | An AWS Budget with email alerts set up *before* anything is deployed - the Well-Architected Cost Optimization pillar in practice, and why Bedrock model charges need special handling |
| [docs/PREFLIGHT_CHECKS.md](docs/PREFLIGHT_CHECKS.md) | Every setup and verification command with its purpose, expected response and common errors - run before the first deploy |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Build, deploy, verify end to end (token, API calls, the refusals) and remove the stack |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | The API contract: authentication, request and response fields, every error, and the limits |
| [docs/WELL_ARCHITECTED_REVIEW.md](docs/WELL_ARCHITECTED_REVIEW.md) | The six-pillar review of the deployed stack: findings, risk ratings and how each was resolved |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Client Application                      │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP/HTTPS + API Key
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                        API Gateway                          │
│               (Authentication, Rate Limiting)               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                     Lambda Functions                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ - Converse API wrapper (streaming + non-streaming)   │   │
│  │ - Request validation & model selection logic         │   │
│  │ - Token counting & cost estimation                   │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                        AWS Bedrock                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ - Claude 3 (Opus, Sonnet, Haiku)                     │   │
│  │ - Other foundation models (optional)                 │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
     ┌───────────────────┼───────────────────┐
     ▼                   ▼                   ▼
┌───────────────┐  ┌────────────────┐  ┌───────────────┐
│  CloudWatch   │  │   CloudWatch   │  │     X-Ray     │
│     Logs      │  │    Metrics     │  │    Traces     │
│   (Debug)     │  │ (Cost, latency)│  │ (Performance) │
└───────────────┘  └────────────────┘  └───────────────┘
```

**Key Components:**
- **API Gateway** - RESTful HTTP endpoint with authentication (Cognito/API keys)
- **Lambda** - Stateless compute layer that calls Bedrock Converse API
- **Bedrock Converse API** - Foundation model invocation (streaming + non-streaming)
- **IAM** - Fine-grained permissions for Lambda → Bedrock
- **CloudWatch** - Logs, metrics, cost analysis
- **X-Ray** - End-to-end request tracing for performance debugging

## What's Included

```
serverless_genai_reference_architecture/
├── bootstrap/                    # One-time account setup (admin runs once)
│   ├── iam/                      # Least-privilege operator roles + permissions boundary
│   └── budget/                   # AWS Budget with email alerts
├── terraform/                    # Infrastructure as Code
│   ├── versions.tf               # Terraform and provider version constraints
│   ├── backend.tf                # S3 remote state (settings from gitignored backend.hcl)
│   ├── providers.tf              # AWS provider, default tags
│   ├── variables.tf / locals.tf  # Inputs and derived names
│   ├── bedrock.tf                # Tagged application inference profile per model alias
│   ├── iam.tf                    # Lambda execution role (with permissions boundary)
│   ├── outputs.tf                # Role ARN, model alias ARNs
│   ├── api_gateway.tf            # REST API, Cognito authorizer, usage plan (phase 2)
│   ├── lambda.tf                 # Lambda function (phase 2)
│   ├── .terraform.lock.hcl       # Pinned provider versions and checksums
│   ├── backend.hcl.example       # Template for backend.hcl
│   └── terraform.tfvars.example  # Template for terraform.tfvars
├── lambda/                       # Lambda function source (Node.js 22, TypeScript)
│   ├── src/handler.ts            # Request validation, model alias resolution, Converse/ConverseStream
│   ├── src/cost.ts               # Token usage → estimated cost, EMF metrics
│   └── package.json              # Dependencies and build scripts
├── docs/                         # Documentation
│   ├── LEARNING_GUIDE.md         # Concepts, request flow, Well-Architected reasoning, exam mapping
│   ├── PREFLIGHT_CHECKS.md       # Setup verification runbook: command, purpose, expected result, errors
│   ├── BUILD_PLAN.md             # Build order and decisions, each mapped to Well-Architected pillars
│   ├── ARCHITECTURE.md           # Detailed architecture & design decisions
│   ├── DEPLOYMENT.md             # Step-by-step deployment guide
│   ├── COST_ANALYSIS.md          # Bedrock pricing & optimization tips
│   ├── API_REFERENCE.md          # REST API endpoint documentation
│   └── WELL_ARCHITECTED_REVIEW.md # Well-Architected audit findings & remediation
├── examples/                     # Example client code
│   ├── python_client.py          # Python HTTP client
│   └── curl_examples.sh          # cURL examples
├── tests/                        # Unit & integration tests
│   ├── handler.test.ts           # Lambda unit tests (Bedrock stubbed)
│   └── test_integration.py       # End-to-end tests
├── .gitignore
├── README.md                     # This file
└── LICENSE                       # MIT License
```

## Quick Start

### Prerequisites
- AWS Account with Bedrock access (Claude models)
- Terraform >= 1.10
- Node.js 22+ (to build the Lambda function)
- Python 3.11+ (example client and integration tests)
- AWS CLI v2, a recent release (2025 or later). Older 2.x versions lack commands this project uses, such as `aws bedrock list-inference-profiles`. Check with `aws --version`

### Deploy

| Step | Guide |
|------|-------|
| 1. One-time account setup (administrator) | [bootstrap/](bootstrap/README.md): least-privilege IAM, Cognito user pool, AWS Budget |
| 2. Verify the account | [docs/PREFLIGHT_CHECKS.md](docs/PREFLIGHT_CHECKS.md) |
| 3. Deploy, verify, remove | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |

In short, once the account is set up:

```bash
npm --prefix lambda ci && npm --prefix lambda test && npm --prefix lambda run build
terraform -chdir=terraform init "-backend-config=backend.hcl"
terraform -chdir=terraform plan -out=tfplan
terraform -chdir=terraform apply tfplan
```

The stack is built in phases ([BUILD_PLAN.md](docs/BUILD_PLAN.md)). Phases 1 and 2 are deployable: the authenticated, rate-limited `/v1/chat` and `/v1/models` endpoints. [DEPLOYMENT.md steps 11-14](docs/DEPLOYMENT.md#11-get-an-access-token) get a token and call the API.

## Key Features

:white_check_mark: **Streaming responses** - Long-running requests don't timeout; responses stream to clients in real-time

:white_check_mark: **Cost observability** - Token counting + real-time cost estimation per request (CloudWatch metrics)

:white_check_mark: **Model flexibility** - Switch between Bedrock models (Claude, Llama, Mistral, etc.) without code changes

:white_check_mark: **Authentication** - API key validation + optional Cognito integration for enterprise IAM

:white_check_mark: **Error handling** - Graceful degradation, retry logic, detailed error messages

:white_check_mark: **Observability** - CloudWatch Logs, X-Ray tracing, custom metrics for latency & cost

:white_check_mark: **Security** - IAM least-privilege, VPC endpoint support, encrypted CloudWatch logs

:white_check_mark: **Terraform modules** - Reusable, production-ready, easy to fork and customize

## Architecture Decisions

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed rationale on:
- Why Lambda + API Gateway (vs. ECS/Fargate)?
- Streaming implementation (chunked transfer encoding)
- Cost tracking strategy
- Authentication approaches
- Scaling patterns

## Well-Architected Review

The deployed stack is audited against all six pillars of the AWS Well-Architected Framework. Findings, risk levels and remediation status are tracked in [docs/WELL_ARCHITECTED_REVIEW.md](docs/WELL_ARCHITECTED_REVIEW.md).

## Cost Estimate

**Per 1M tokens (typical month):**
- Bedrock (Claude 3 Sonnet) - ~$3–5
- Lambda (compute) - <$1
- API Gateway - <$1
- CloudWatch (logs + metrics) - ~$1–2
- **Total - ~$5–9 per million tokens**

See [docs/COST_ANALYSIS.md](docs/COST_ANALYSIS.md) for detailed breakdown and cost optimization tips.

## Exam Alignment (AWS Certified Generative AI Developer – Professional)

This build aligns with **AIP-C01 Domains 1 & 2:**

| Domain | Topics Covered |
|--------|----------------|
| **D1: Foundation Model Integration (31%)** | Bedrock Converse API, model selection, prompt engineering, token counting |
| **D2: Implementation & Integration (26%)** | Lambda, API Gateway, IAM, error handling, streaming, observability |

## What's Next

This is the foundation for a series of builds that extend it into a complete GenAI platform on AWS:
- **RAG** - Bedrock Knowledge Bases, embeddings, managed vector store
- **Security & guardrails** - Bedrock Guardrails, VPC endpoints, KMS, invocation logging
- **Agents** - Bedrock Agents / AgentCore with Lambda action groups
- **Evaluation, monitoring & cost routing** - model evaluation, prompt caching, model routing

## Contributing

This is a reference architecture - feel free to fork, customize, and share improvements. Link back to this repo if you publish enhancements.

## License

MIT License - see [LICENSE](LICENSE) file.

---

**Questions?** See the docs or file an issue.

**Want to learn more?** Start with [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) or [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
