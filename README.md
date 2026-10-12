markdown
# Serverless GenAI Reference Architecture

A production-ready template for building Generative AI APIs on AWS using managed serverless services.

## Overview

This repository provides a reusable, enterprise-grade reference architecture for deploying foundation models via REST APIs without managing servers. It combines AWS Bedrock, Lambda, API Gateway, and observability to deliver a scalable, secure, cost-conscious pattern for GenAI applications.

**Perfect for:**
- Teams building internal GenAI APIs
- Proof-of-concepts that need to scale quickly
- Organizations evaluating Bedrock costs and performance
- Learning AWS GenAI best practices (AWS Certified Generative AI Developer – Professional)

## Architecture

┌─────────────────────────────────────────────────────────────┐
│                     Client Application                       │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP/HTTPS + API Key
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    API Gateway                               │
│              (Authentication, Rate Limiting)                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  Lambda Functions                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ - Converse API wrapper (streaming + non-streaming)  │   │
│  │ - Request validation & model selection logic        │   │
│  │ - Token counting & cost estimation                  │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  AWS Bedrock                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ - Claude 3 (Opus, Sonnet, Haiku)                    │   │
│  │ - Other foundation models (optional)                │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
     ┌───────────────────┼───────────────────┐
     ▼                   ▼                   ▼
┌─────────────┐  ┌──────────────┐  ┌──────────────┐
│ CloudWatch  │  │  CloudWatch  │  │  X-Ray       │
│   Logs      │  │   Metrics    │  │  Traces      │
│  (Debug)    │  │ (Cost, latency)│  │(Performance) │
└─────────────┘  └──────────────┘  └──────────────┘
**Key Components:**
- **API Gateway** — RESTful HTTP endpoint with authentication (Cognito/API keys)
- **Lambda** — Stateless compute layer that calls Bedrock Converse API
- **Bedrock Converse API** — Foundation model invocation (streaming + non-streaming)
- **IAM** — Fine-grained permissions for Lambda → Bedrock
- **CloudWatch** — Logs, metrics, cost analysis
- **X-Ray** — End-to-end request tracing for performance debugging

## What's Included

serverless_genai_reference_architecture/
├── terraform/                    # Infrastructure as Code
│   ├── main.tf                  # Main resource definitions
│   ├── variables.tf             # Input variables
│   ├── outputs.tf               # Stack outputs (endpoint URL, etc.)
│   ├── iam.tf                   # IAM roles & policies
│   ├── api_gateway.tf           # API Gateway + auth
│   ├── lambda.tf                # Lambda function config
│   └── terraform.tfvars.example # Example variable values[1:28 PM]├── lambda/                       # Lambda function source
│   ├── converse.py             # Bedrock Converse wrapper
│   ├── utils.py[1:28 PM]# Token counting, cost calc, logging
│   └── requirements.txt         # Python dependencies
├── docs/                        # Documentation
│   ├── ARCHITECTURE.md          # Detailed architecture & design decisions
│   ├── DEPLOYMENT.md            # Step-by-step deployment guide
│   ├── COST_ANALYSIS.md         # Bedrock pricing & optimization tips
│   └── API_REFERENCE.md         # REST API endpoint documentation
├── examples/                    # Example client code
│   ├── python_client.py        # Python HTTP client
│   └── curl_examples.sh        # cURL examples
├── tests/                       # Unit & integration tests
│   ├── test_converse.py        # Lambda function tests
│   └── test_integration.py     # End-to-end tests
├── .gitignore
├── README.md                   # This file
└── LICENSE                     # MIT License
## Quick Start

### Prerequisites
- AWS Account with Bedrock access (Claude models)
- Terraform >= 1.0
- Python 3.11+
- AWS CLI v2 configured with credentials

### Deploy

1. **Clone & configure:**
   ```bash
   git clone https://github.com/cr3datatech/serverless_genai_reference_architecture.git
   cd serverless_genai_reference_architecture/terraform
   
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your values (region, project name, etc.)
   



2. **Deploy to AWS:**
   bash
   terraform init
   terraform plan
   terraform apply
   



3. **Test the API:**
   bash
   # Get your API endpoint from Terraform outputs
   API_KEY=$(terraform output -raw api_key)
   ENDPOINT=$(terraform output -raw api_gateway_endpoint)
   
   curl -X POST "$ENDPOINT/chat" \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "model": "claude-3-sonnet-20240229",
       "messages": [{"role": "user", "content": "Hello, Claude!"}],
       "stream": false
     }'
   



## Key Features

:white_check_mark: **Streaming responses** — Long-running requests don't timeout; responses stream to clients in real-time

:white_check_mark: **Cost observability** — Token counting + real-time cost estimation per request (CloudWatch metrics)

:white_check_mark: **Model flexibility** — Switch between Bedrock models (Claude, Llama, Mistral, etc.) without code changes

:white_check_mark: **Authentication** — API key validation + optional Cognito integration for enterprise IAM

:white_check_mark: **Error handling** — Graceful degradation, retry logic, detailed error messages

:white_check_mark: **Observability** — CloudWatch Logs, X-Ray tracing, custom metrics for latency & cost

:white_check_mark: **Security** — IAM least-privilege, VPC endpoint support, encrypted CloudWatch logs

:white_check_mark: **Terraform modules** — Reusable, production-ready, easy to fork and customize

## Architecture Decisions

See docs/ARCHITECTURE.md for detailed rationale on:
- Why Lambda + API Gateway (vs. ECS/Fargate)?
- Streaming implementation (chunked transfer encoding)
- Cost tracking strategy
- Authentication approaches
- Scaling patterns

## Cost Estimate

**Per 1M tokens (typical month):**
- Bedrock (Claude 3 Sonnet) — ~$3–5
- Lambda (compute) — <$1
- API Gateway — <$1
- CloudWatch (logs + metrics) — ~$1–2
- **Total — ~$5–9 per million tokens**

See docs/COST_ANALYSIS.md for detailed breakdown and cost optimization tips.

## Exam Alignment (AWS Certified Generative AI Developer – Professional)

This build aligns with **AIP-C01 Domains 1 & 2:**

| Domain | Topics Covered |
|--------|----------------|
| **D1: Foundation Model Integration (31%)** | Bedrock Converse API, model selection, prompt engineering, token counting |
| **D2: Implementation & Integration (26%)** | Lambda, API Gateway, IAM, error handling, streaming, observability |

## What's Next

**Cycle 2 (Oct 25–Nov 8):** Build #2 **RAG Knowledge Assistant** on top of this foundation.
- Add OpenSearch for document retrieval[1:28 PM]- Implement prompt engineering for RAG patterns
- Cost tracking for retrieval-augmented requests

**Cycles 3–5:** Bedrock Agents, guardrails, advanced monitoring.

## Contributing

This is a reference ar
[1:28 PM]chitecture — feel free to fork, customize, and share improvements. Link back to this repo if you publish enhancements.

## License

MIT License — see LICENSE file.

---

**Questions?** See the docs or file an issue.

**Want to learn more?** Start with docs/ARCHITECTURE.md or docs/DEPLOYMENT.md.