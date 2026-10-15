# Learning Guide

This guide explains **what** this repository builds, **how** each piece works, and **why** every design choice was made. It is written for someone learning AWS generative AI - in particular anyone preparing for the **AWS Certified Generative AI Developer – Professional (AIP-C01)** exam - who wants to understand the architecture, not just deploy it.

Every decision in this project is justified against the **AWS Well-Architected Framework**. Well-Architected is not a final checklist bolted on at the end; it is the lens used to make each choice, and the finished stack is audited against it ([WELL_ARCHITECTED_REVIEW.md](WELL_ARCHITECTED_REVIEW.md)). Wherever you see a 🏛️ marker below, the text explains which Well-Architected pillar a choice serves.

**Suggested reading order**

1. [The problem](#1-the-problem-this-solves) - why put a model behind an API at all
2. [Well-Architected primer](#2-the-aws-well-architected-framework) - the framework every decision is measured against
3. [A request, end to end](#3-a-request-end-to-end) - follow one call through the system
4. [Component deep dives](#4-component-deep-dives) - Bedrock, Lambda, API Gateway, IAM, observability, Terraform
5. [Decisions mapped to Well-Architected](#5-every-decision-mapped-to-well-architected) - the "why" in one table
6. [Exam mapping](#6-aip-c01-exam-mapping), [self-check questions](#7-self-check-questions), [glossary](#8-glossary), [further reading](#9-further-reading)

Then read [BUILD_PLAN.md](BUILD_PLAN.md) for the build order and [bootstrap/iam](../bootstrap/iam/README.md) for the security foundation.

---

## 1. The problem this solves

Amazon Bedrock lets any application with AWS credentials call a foundation model (FM) such as Claude directly. So why build an API in front of it?

Because once more than one application, team, or person uses a model, you need answers to questions a direct call can't give you:

| Question | Without a central API | With this architecture |
|---|---|---|
| Who is calling, and are they allowed to? | Every app needs its own AWS credentials with Bedrock rights | One authenticated endpoint; clients never hold Bedrock permissions |
| Which models may be used? | Any model the credentials allow - including the most expensive | A server-side allowlist of approved models behind simple aliases |
| What is it costing, and who is spending it? | Visible only on the monthly bill, per account | Per-request tokens and estimated cost, as metrics, per model and client |
| How do we stop runaway usage? | Nothing short of revoking credentials | Rate limits, quotas, concurrency caps and token caps |
| Is it healthy, and how fast is it? | Each app instruments itself, or doesn't | Central logs, latency metrics, traces, dashboards and alarms |
| How do we change models? | Code change in every client | A configuration change in one place |

This is sometimes called an **LLM gateway** or **GenAI gateway** pattern. It is the foundation that retrieval-augmented generation (RAG), guardrails, agents and model routing are later added to.

🏛️ **Well-Architected:** centralising access is itself a Well-Architected decision. It serves **Security** (one place to authenticate and authorise), **Cost Optimization** (one place to measure and limit spend), and **Operational Excellence** (one place to observe and change behaviour).

---

## 2. The AWS Well-Architected Framework

### What it is

The [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html) is AWS's documented set of best practices for building and running workloads in the cloud. It is organised into **six pillars**, each with design principles, questions, and numbered best practices (for example `SEC02-BP02 - Use temporary credentials`).

| Pillar | The question it asks | What it means for a GenAI API |
|---|---|---|
| **Operational Excellence** | Can you run, observe and improve it safely? | Infrastructure as code, structured logs, dashboards, alarms, runbooks, safe deploys |
| **Security** | Is access controlled, data protected, and activity traceable? | Authentication, least-privilege IAM, permissions boundaries, no secrets in code, audit trail, minimal logging of sensitive prompts |
| **Reliability** | Does it withstand and recover from failure? | Handling Bedrock throttling, timeouts and retries; managed multi-AZ services; quotas understood |
| **Performance Efficiency** | Are resources chosen and used efficiently as demand changes? | Streaming for responsiveness, right-sized Lambda, appropriate model per task |
| **Cost Optimization** | Do you understand and control spend? | Token-level cost visibility, model allowlists, quotas, pay-per-use services, arm64 |
| **Sustainability** | Do you minimise environmental impact? | Serverless (no idle capacity), Graviton/arm64, smallest model that does the job, no unnecessary data retention |

### Lenses

A **lens** extends the framework with guidance for a specific kind of workload. Two apply directly here:

- **[Generative AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/generative-ai-lens.html)** - model selection, prompt and response handling, responsible AI, cost of inference, observability of model calls.
- **[Serverless Applications Lens](https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/welcome.html)** - Lambda, API Gateway and event-driven design.

### How this repository uses it

1. **Design time** - every decision in [BUILD_PLAN.md](BUILD_PLAN.md) names the pillar(s) it serves and the trade-off it accepts. Section 5 of this guide collects them in one table.
2. **Build time** - the IAM foundation ([bootstrap/iam](../bootstrap/iam/README.md)) applies Security best practices *before* any workload exists: least privilege, temporary credentials, MFA, and permissions boundaries.
3. **Review time** - the deployed stack is assessed against all six pillars with a read-only, evidence-based review. Findings are rated with Well-Architected risk levels:
   - **HRI (High Risk Issue)** - a plausible, near-term path to outage, breach, data loss or material unplanned cost
   - **MRI (Medium Risk Issue)** - real risk, but mitigated or dependent on another failure
4. **Remediation** - HRIs are fixed before release; MRIs are fixed or recorded as accepted risks with a reason; the stack is re-reviewed. Results are published in [WELL_ARCHITECTED_REVIEW.md](WELL_ARCHITECTED_REVIEW.md).

Well-Architected deliberately produces **no numeric score**. It produces a list of risks and the decisions taken about them. Trade-offs are expected: for example, logging full prompts helps debugging (Operational Excellence) but increases data exposure (Security). The framework's value is that the trade-off is made consciously and written down.

> **Exam tip:** AIP-C01 questions are often framed as "which solution meets the requirements with the LEAST operational overhead / MOST cost-effectively / MOST securely". Those qualifiers map directly onto Well-Architected pillars. Learning to ask "which pillar is this question optimising for?" is one of the most useful exam skills.

---

## 3. A request, end to end

Follow a single call to `POST /v1/chat`:

```
 ① Client ──HTTPS──► ② API Gateway ──► ③ Lambda ──► ④ Bedrock (Claude)
                         │                 │              │
                         ▼                 ▼              ▼
                  ⑤ access log      ⑥ structured log   ⑦ token usage
                     X-Ray trace       EMF metrics        returned to Lambda
                     throttle check    X-Ray subsegment
```

| Step | What happens | What can go wrong | 🏛️ Pillar |
|---|---|---|---|
| ① **Client** sends JSON with a model *alias* (`fast`, `balanced`, `best`), messages, and `stream` true/false, plus credentials | Wrong or missing credentials | Security |
| ② **API Gateway** authenticates the caller, checks the API key against a **usage plan** (throttle + quota), validates basic request shape, then invokes Lambda | Over quota → `429`; unauthenticated → `401/403` | Security, Reliability, Cost |
| ③ **Lambda** validates the body (size, `max_tokens` cap, allowed roles), resolves the alias to an **allowlisted model ID**, and calls the Bedrock **Converse** (or **ConverseStream**) API | Invalid input → `400`; unknown alias → `400` | Security, Cost |
| ④ **Bedrock** runs the model. The request goes to an **inference profile** that may route it to another region in the same geography with spare capacity | Bedrock throttling → mapped to `429`; model not enabled → `500` with a safe message | Reliability, Performance |
| ⑤⑥⑦ Lambda reads **token usage** from the response, multiplies by a price table to estimate cost, writes one structured log line that also carries **metrics** (EMF), and returns the answer (or streams it) | - | Operational Excellence, Cost |

The response includes the answer, token counts, an estimated cost, and a request ID that links the client's view to logs and traces.

---

## 4. Component deep dives

### 4.1 Amazon Bedrock

**What it is.** A fully managed service that provides foundation models from several providers (Anthropic, Amazon, Meta, Mistral and others) through one API. You don't manage servers, GPUs, or model weights; you pay per token.

**Key concepts**

- **Foundation model (FM)** - a large pre-trained model. Each has a **model ID** such as `anthropic.claude-…`.
- **Tokens** - models read and write *tokens* (roughly ¾ of an English word). You are billed for **input tokens** (your prompt, including system prompt and conversation history) and **output tokens** (the answer). Output tokens usually cost several times more than input tokens.
- **Converse API** - a single, model-agnostic request/response format (`messages`, `system`, `inferenceConfig`) that works across Bedrock models. Switching models doesn't require changing request code. The response includes a `usage` block with token counts.
- **ConverseStream** - the streaming variant. The model's answer arrives as a series of events (`contentBlockDelta`) while it is generated, followed by a `metadata` event containing usage.
- **Inference profiles (cross-region inference)** - instead of calling a model in one region, you call a profile (for example one with an `eu.` prefix) that can route the request to any region in that geography with available capacity. This raises throughput and resilience, and geographic profiles keep data within that geography. Many newer models are only available through inference profiles.
- **Quotas** - Bedrock limits requests per minute and tokens per minute per model per account. Exceeding them returns a `ThrottlingException`.
- **Model access** - some providers require a one-time agreement or use-case form before their models can be invoked in an account.

**Choices in this project and why**

| Choice | 🏛️ Pillar | Reasoning |
|---|---|---|
| Use the **Converse API** rather than model-specific `InvokeModel` payloads | Operational Excellence, Performance Efficiency | One code path for every model; changing model is configuration, not code |
| Expose **aliases** (`fast`/`balanced`/`best`), resolved server-side against an **allowlist** | Cost Optimization, Security | Clients can't select arbitrary or expensive models; models can be upgraded without client changes |
| Call through **geographic inference profiles** | Reliability, Performance Efficiency, Security | More capacity and fewer throttles; data stays in the chosen geography (data residency) |
| Cap `max_tokens` server-side | Cost Optimization, Reliability | Bounds the cost and duration of any single request |
| Map `ThrottlingException` to HTTP `429` with a retry hint | Reliability | Clients back off correctly instead of failing hard or hammering the service |

### 4.2 AWS Lambda

**What it is.** Serverless compute: you upload a function, AWS runs it on demand, and you pay per request and per millisecond of execution. There are no servers to patch and no idle cost.

**Key concepts**

- **Execution role** - the IAM role the function runs as. It decides what the function may call (here: Bedrock invoke, write its own logs and traces - nothing else).
- **Cold start** - the first invocation in a new execution environment pays a start-up delay. Small deployment packages and lightweight runtimes reduce it.
- **Concurrency** - each concurrent request uses one execution environment. **Reserved concurrency** sets a maximum for a function, which is also a hard cap on how many Bedrock calls can run at once.
- **Architecture** - functions can run on x86_64 or **arm64 (AWS Graviton)**. arm64 is cheaper per GB-second and more energy-efficient.
- **Response streaming** - a function can send its response in pieces as they are produced instead of all at once. Native support exists for Node.js managed runtimes; other languages need a custom runtime or the AWS Lambda Web Adapter. Streaming also allows responses longer than the normal payload limit and up to the function's timeout (maximum 15 minutes).

**Choices in this project and why**

| Choice | 🏛️ Pillar | Reasoning |
|---|---|---|
| Lambda rather than containers (ECS/Fargate) | Operational Excellence, Cost Optimization, Sustainability | Requests are short and bursty; no servers or idle capacity; scales to zero |
| **arm64 (Graviton)** | Cost Optimization, Sustainability | Lower price per GB-second and lower energy use for the same work |
| **Reserved concurrency** cap | Cost Optimization, Reliability | Hard limit on simultaneous model calls - protects both the bill and the account's Bedrock quota |
| **Streaming** responses | Performance Efficiency | Users see the first words in about a second instead of waiting for the full answer; long answers don't hit request timeouts |
| Minimal execution role, capped by a **permissions boundary** | Security | Even a mistaken policy can't give the function more than the boundary allows |

### 4.3 Amazon API Gateway

**What it is.** A managed service for publishing HTTP APIs. It handles TLS, authentication, throttling, request validation and logging so the code behind it doesn't have to.

**The three ways to put Lambda behind HTTP**

| | REST API | HTTP API | Lambda Function URL |
|---|---|---|---|
| API keys & usage plans (per-client quotas) | ✅ | ❌ | ❌ |
| Authorizers | IAM, Cognito, Lambda | IAM, JWT, Lambda | IAM or none |
| Response streaming | ✅ (Lambda proxy) | ❌ | ✅ |
| AWS WAF integration | ✅ | ❌ | ❌ |
| Native X-Ray tracing | ✅ | ❌ | (via Lambda) |
| Price per request | Higher | Lower | No extra charge |

This project uses a **REST API**: it is the only option offering per-client usage plans, WAF and streaming together.

**Key concepts**

- **Stage** - a named deployment of the API (for example `v1`) with its own settings, logs and throttles.
- **Usage plan** - throttling (requests per second, burst) and quota (requests per day/month) attached to one or more **API keys**. API keys *identify and meter* clients; AWS guidance is not to rely on them as the only authentication.
- **Authorizer** - the component that decides whether a caller is authenticated: IAM (SigV4 signed requests), Amazon Cognito (JWT tokens), or a custom Lambda function.
- **Integration timeout** - non-streaming integrations have a maximum wait time; streaming integrations can run much longer.

**Choices in this project and why**

| Choice | 🏛️ Pillar | Reasoning |
|---|---|---|
| REST API with **usage plans** | Cost Optimization, Reliability | Per-client throttle and quota; one client can't starve others or run up cost |
| **Real authentication** in addition to API keys (see [BUILD_PLAN.md](BUILD_PLAN.md) D2) | Security | API keys alone are identifiers, not credentials |
| **Access logging** and **X-Ray tracing** on the stage | Operational Excellence | Every request is recorded and traceable end to end |
| **Stage-level throttling** as a global ceiling | Reliability, Cost Optimization | Protects the backend even if a usage plan is misconfigured |

### 4.4 IAM: least privilege and permissions boundaries

IAM decides who can do what. This project applies the Security pillar before any workload exists, in [bootstrap/iam](../bootstrap/iam/README.md).

**Key concepts**

- **User vs role** - a *user* has long-lived credentials; a *role* is assumed and gives **temporary credentials** that expire. Well-Architected best practice `SEC02-BP02` is to use temporary credentials.
- **Least privilege** - grant only the actions and resources needed. Here, deployment rights are limited to resources named `powerlab-*`.
- **The `PassRole` escalation problem** - anyone who can create an IAM role and pass it to a service (like Lambda) can create an all-powerful role and run code with it, escalating their own privileges.
- **Permissions boundary** - a managed policy attached to a role that sets the *maximum* permissions the role can ever have, whatever other policies are attached. Effective permissions = identity policy ∩ boundary.

**How the bootstrap uses them**

| Control | 🏛️ Pillar | Reasoning |
|---|---|---|
| Operator user can *only* assume roles, and only with **MFA** | Security | A leaked access key alone can do nothing |
| Separate **deploy** and **review** roles | Security | The review runs read-only and can't change what it audits (separation of duties) |
| Deploy role may create roles **only if they carry the boundary** | Security | Closes the `PassRole` escalation path |
| Boundary can't be removed; control-plane roles and policies are protected by an explicit deny | Security | The deploy role can't widen its own rights |
| Everything scoped to `powerlab-*` and tagged | Security, Operational Excellence | Safe to deploy into a shared account; the review can be scoped to this stack |

### 4.5 Observability: logs, metrics, traces and alarms

**Key concepts**

- **Structured logs** - one JSON object per event (request ID, model, tokens, latency, outcome) instead of free text, so logs can be queried with CloudWatch Logs Insights.
- **Embedded Metric Format (EMF)** - a log line in a special JSON shape that CloudWatch automatically turns into metrics. One line gives you both a log record and metrics (tokens, cost, latency) without extra API calls.
- **AWS X-Ray** - distributed tracing. Each request gets a trace showing time spent in API Gateway, Lambda and the Bedrock call.
- **Alarms** - CloudWatch alarms on error rates, throttles, latency and estimated cost, sending notifications (via SNS) when thresholds are crossed.

**Choices in this project and why**

| Choice | 🏛️ Pillar | Reasoning |
|---|---|---|
| Per-request **token and cost metrics** by model | Cost Optimization | Cost becomes visible daily, per model, instead of monthly on the bill |
| **Metadata-only logging** by default (no prompt or response text) | Security | Prompts can contain personal or confidential data; don't store it unless there is a reason |
| X-Ray tracing on every request | Operational Excellence, Performance Efficiency | Shows whether latency is in the gateway, the function or the model |
| Alarms with a **cost threshold** | Cost Optimization, Operational Excellence | Unexpected spend is caught within a day, not at month end |
| Log **retention** set explicitly | Cost Optimization, Sustainability | Logs don't accumulate forever by default |

### 4.6 Terraform: infrastructure as code

**Key concepts**

- **Declarative IaC** - you describe the desired end state; Terraform works out what to create, change or delete (`plan`), then does it (`apply`).
- **State** - Terraform records what it manages in a state file. Stored remotely in S3 with locking, so it is shared, versioned and can't be corrupted by two runs at once.
- **Default tags** - tags applied automatically to every resource the provider creates.

**Choices in this project and why**

| Choice | 🏛️ Pillar | Reasoning |
|---|---|---|
| All infrastructure in Terraform; nothing created by hand | Operational Excellence, Reliability | Repeatable, reviewable, and reversible - `destroy` removes everything |
| Remote, versioned, encrypted **state with locking** | Reliability, Security | State is recoverable and never edited concurrently |
| **Default tags** on everything | Cost Optimization, Operational Excellence | Cost allocation and review scoping |
| Account-specific values only in gitignored files (`terraform.tfvars`, `backend.hcl`) | Security | The repository can be public without exposing the deploying account |

---

## 5. Every decision, mapped to Well-Architected

The full reasoning is in [BUILD_PLAN.md](BUILD_PLAN.md). This is the summary view.

| Decision | OPS | SEC | REL | PERF | COST | SUS |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Central API in front of Bedrock | ● | ● | | | ● | |
| Serverless (Lambda + API Gateway + Bedrock) | ● | | ● | | ● | ● |
| REST API with usage plans and stage throttling | | | ● | | ● | |
| Authentication beyond API keys | | ● | | | | |
| Converse API + server-side model aliases and allowlist | ● | ● | | ● | ● | |
| Geographic cross-region inference profiles | | ● | ● | ● | | |
| Response streaming | | | | ● | | |
| arm64 (Graviton) | | | | | ● | ● |
| Reserved concurrency and `max_tokens` caps | | | ● | | ● | |
| Least-privilege roles + permissions boundary | | ● | | | | |
| MFA-gated, temporary deploy credentials | | ● | | | | |
| Structured logs, EMF metrics, X-Ray, alarms | ● | | ● | ● | ● | |
| Metadata-only logging by default | | ● | | | | ● |
| Terraform with remote locked state and default tags | ● | ● | ● | | ● | |

*OPS = Operational Excellence · SEC = Security · REL = Reliability · PERF = Performance Efficiency · COST = Cost Optimization · SUS = Sustainability*

---

## 6. AIP-C01 exam mapping

| Exam domain | Concepts practised in this build | Where |
|---|---|---|
| **Domain 1 - Foundation Model Integration, Data Management & Compliance** | Model selection and aliases, Converse API, inference parameters, token usage, inference profiles and data residency | §4.1, Lambda handler |
| **Domain 2 - Implementation & Integration** | Lambda, API Gateway (REST vs HTTP vs Function URL), streaming, authentication, IAM, error handling and retries, observability | §4.2–4.5, Terraform |
| **Domain 3 - AI Safety, Security & Governance** *(foundations)* | Least privilege, permissions boundaries, temporary credentials, prompt-logging policy | §4.4, bootstrap |
| **Domain 4 - Operational Efficiency & Optimization** *(foundations)* | Token cost tracking, quotas, concurrency caps, arm64 | §4.2, §4.5 |
| **Domain 5 - Testing, Validation & Troubleshooting** *(foundations)* | Tracing, structured logs, alarms, integration tests | §4.5, tests |

Later builds in the same series go deeper into Domains 3–5 (guardrails, evaluation, model routing, prompt caching).

---

## 7. Self-check questions

Answer these without looking; the answers are in the sections above.

1. Name the six Well-Architected pillars, and give one decision in this project that serves each.
2. What does the Converse API give you that `InvokeModel` doesn't?
3. Why might a request sent to Bedrock in one region actually be processed in another region, and why is that acceptable here?
4. What is the difference between an API key and an authorizer in API Gateway? Why isn't an API key enough on its own?
5. You need per-client quotas *and* streaming responses. Which API Gateway type do you choose, and why not the others?
6. Explain the `PassRole` privilege-escalation problem, and how a permissions boundary prevents it.
7. Why is token usage read from every response rather than estimated from the bill?
8. Give two independent mechanisms in this design that limit runaway cost.
9. A Bedrock call returns `ThrottlingException`. What should the API return to the client, and why?
10. Logging full prompts would make debugging easier. Which pillar argues against it, and how is the trade-off resolved here?
11. Why is arm64 a Sustainability decision as well as a Cost decision?
12. What is the difference between an HRI and an MRI, and what happens to each before release?

---

## 8. Glossary

| Term | Meaning |
|---|---|
| **Alias (model)** | A stable name (`fast`, `balanced`, `best`) mapped server-side to a specific model ID |
| **Converse / ConverseStream** | Bedrock's model-agnostic chat APIs, non-streaming and streaming |
| **EMF** | Embedded Metric Format - log lines that CloudWatch turns into metrics |
| **FM** | Foundation model - a large pre-trained model available through Bedrock |
| **HRI / MRI** | High / Medium Risk Issue - Well-Architected risk ratings |
| **Inference profile** | A Bedrock routing target that spreads requests across regions in a geography |
| **Lens** | A Well-Architected extension for a workload type (e.g. Generative AI, Serverless) |
| **Permissions boundary** | A policy setting the maximum permissions an IAM role can have |
| **Reserved concurrency** | A fixed cap on simultaneous executions of a Lambda function |
| **Stage** | A named, versioned deployment of an API Gateway API |
| **Temporary credentials** | Short-lived credentials from assuming a role; expire automatically |
| **Token** | The unit models read and write, and the unit Bedrock bills by |
| **Usage plan** | API Gateway throttle and quota settings attached to API keys |

---

## 9. Further reading

- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html)
- [Well-Architected Generative AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/generative-ai-lens.html)
- [Well-Architected Serverless Applications Lens](https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/welcome.html)
- [Amazon Bedrock - Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)
- [Amazon Bedrock - Cross-region inference](https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html)
- [AWS Lambda - Response streaming](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html)
- [API Gateway - Usage plans and API keys](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-api-usage-plans.html)
- [IAM - Permissions boundaries](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html)
- [CloudWatch - Embedded Metric Format](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format.html)
