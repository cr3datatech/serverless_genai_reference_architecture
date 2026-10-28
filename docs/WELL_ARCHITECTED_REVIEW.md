# Well-Architected Review

This architecture is audited against the six pillars of the [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html), with the [Generative AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/generative-ai-lens.html) where it applies. The review was run against the deployed stack, its findings were fixed or given a documented disposition, and the stack was then re-assessed to confirm the fixes.

> **Status:** Reviewed 2026-10-19 (A1, workload review); re-assessed 2026-10-20 (A6, after remediation) and 2026-10-28 (A6, after the quota increase). **No open risks** for the workload, down from 0 high, 3 medium and 3 low.

## Method

| | |
|---|---|
| **Scope** | The resources this repo deploys (API Gateway, Lambda, IAM, Bedrock inference profiles, Cognito app client and domain, CloudWatch, SNS, X-Ray), the bootstrap identities and budget, and the Terraform state bucket, in one region |
| **Account** | A shared account that also runs other workloads. Account-level controls the stack does not create (CloudTrail, GuardDuty and similar) were observed and are reported as **account context**, separately from the workload's own findings |
| **Identity** | The read-only review role from [bootstrap/iam](../bootstrap/iam/README.md) (AWS `ReadOnlyAccess`, MFA required), so the review can't change what it examines |
| **Tooling** | The AWS-Best-Practices-Agent-Team assessment toolkit: a baseline sweep of read-only API calls, deep dives (IAM, S3, Compute Optimizer, Cost Explorer, Config, Well-Architected Tool) and targeted reads of each resource. Every call, including failures, is recorded as evidence |
| **Evidence rule** | Every finding cites a Well-Architected best-practice ID and the configuration evidence behind it. A finding is marked remediated only when new evidence shows the fix, not on the strength of a change having been made |
| **Assessment types** | **A1**, full workload review against all six pillars. **A6**, re-assessment: the same sweep with the same scope, diffed against the previous assessment |
| **Framework edition** | Best-practice IDs follow the Well-Architected Framework published November 6, 2024. AWS renumbers best practices between editions |
| **What's published here** | Pillar verdicts, findings and their dispositions. Account identifiers, resource ARNs and raw evidence are not published |

## Risk levels

| Level | Meaning |
|-------|---------|
| 🔴 **High (HRI)** | A plausible, near-term path to outage, breach, data loss, or material unplanned cost |
| 🟠 **Medium (MRI)** | Real risk, but mitigated, bounded, or dependent on another failure first |
| 🟡 **Low** | Best-practice deviation with limited practical impact |
| 🟢 **None** | Practice met - recorded to show it was checked |

Only **open** findings count in the scorecard. The other dispositions are **remediated** (fixed, with evidence), **accepted risk** (kept deliberately, with an owner and a reason), **deferred** (planned for a later build, or owned outside the workload) and **not applicable**.

## Scorecard

Open findings for the workload, per pillar, after each assessment. The A1 column shows the starting point.

| Pillar | A1 2026-10-19 (H / M / L) | A6 2026-10-20 | A6 2026-10-28 | Verdict |
|--------|------|------|------|---------|
| Operational Excellence | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | ✅ Practices met: the whole workload is code, tagged, with runbooks and tests |
| Security | 0 / 1 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | ✅ Least privilege, authentication on every method, metadata-only logs; refused requests are now logged. WAF and invocation logging are deferred to the security build |
| Reliability | 0 / 1 / 1 | 0 / 1 / 0 | 0 / 0 / 0 | ✅ Alarms, tracing and deletion protection in place; the account's Lambda concurrency is now the default 1000 |
| Performance Efficiency | 0 / 0 / 1 | 0 / 0 / 0 | 0 / 0 / 0 | ✅ Compute Optimizer enrolled; a memory recommendation appears once there is enough invocation history |
| Cost Optimization | 0 / 1 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | ✅ Spend bounded by quotas, throttles, a token cap, an alarm and a budget; costs now attributable by tag |
| Sustainability | 0 / 0 / 1 | 0 / 0 / 0 | 0 / 0 / 0 | ✅ Arm64 serverless, no idle resources, short retention; old state versions now expire |
| **Total** | **0 / 3 / 3** | **0 / 1 / 0** | **0 / 0 / 0** | |

**Account context** (not counted above, owned by the account owner): no CloudTrail trail (rated high for the account), and GuardDuty, Security Hub, AWS Config and IAM Access Analyzer not enabled (medium). See [Account context](#account-context).

## Findings

| ID | Pillar | Best practice | Risk | Finding | Remediation | Status |
|----|--------|---------------|------|---------|-------------|--------|
| F-001 | Reliability | REL01-BP04 | 🟠 Medium | The account's Lambda concurrency quota was 10 (AWS default 1000) and is shared with other workloads. At 5 requests per second and model calls of several seconds, peak demand could exceed it, and the excess would fail | Default 1000 requested through Service Quotas ([PREFLIGHT 8.1](PREFLIGHT_CHECKS.md#81-lambda-concurrency-quota-reliability-rel01-bp04)) and granted. The throttles alarm stays | ✅ Remediated (A6, 2026-10-28): account limit 1000, request closed |
| F-002 | Cost Optimization | COST03-BP02 | 🟠 Medium | The `Project` cost allocation tag was inactive, so model spend couldn't be attributed to the stack in Cost Explorer | Tag activated ([PREFLIGHT 8.2](PREFLIGHT_CHECKS.md#82-cost-allocation-tag-cost-optimization-cost03-bp02)) | ✅ Remediated (A6) |
| F-003 | Security | SEC04-BP01 | 🟠 Medium | Requests refused by API Gateway (bad token, no API key, throttled) left no record of who sent them: no access log | Account logging role set ([PREFLIGHT 5.1](PREFLIGHT_CHECKS.md#51-account-level-cloudwatch-role)) and `enable_access_logs = true`. One JSON line per request with caller IP, client, API key, status and error type, never content. Stage tracing stays optional ([PREFLIGHT 5.2](PREFLIGHT_CHECKS.md#52-x-ray-tracing-on-the-api-stage-optional)) | ✅ Remediated (A6): a refused request was seen in the log |
| F-006 | Reliability | REL09-BP01 | 🟡 Low | The Cognito user pool had deletion protection off; deleting it would invalidate every client credential | Protection turned on; the bootstrap now creates the pool protected ([PREFLIGHT 8.3](PREFLIGHT_CHECKS.md#83-cognito-deletion-protection-reliability-rel09-bp01)) | ✅ Remediated (A6) |
| F-008 | Sustainability | SUS04-BP03 | 🟡 Low | The Terraform state bucket kept every old state version forever | Lifecycle rule: keep the newest 10 earlier versions and anything from the last 90 days ([DEPLOYMENT step 3](DEPLOYMENT.md#3-create-the-terraform-state-bucket)). Server access logging not added: the bucket is private, versioned and encrypted, and holds no secrets | ✅ Remediated (A6) |
| F-010 | Performance Efficiency | PERF02-BP01 | 🟡 Low | The function's memory (256 MB) was chosen without measured sizing data | Compute Optimizer enrolled ([PREFLIGHT 8.4](PREFLIGHT_CHECKS.md#84-compute-optimizer-performance-efficiency-perf02-bp01)); review its recommendation after 14 days of traffic | ✅ Remediated (A6) |
| F-004 | Security | SEC05-BP03 | 🟠 Medium | No AWS WAF web ACL on the public API endpoint | Mitigated by a mandatory token and API key, throttles, a daily quota and strict validation. WAF (about $5/month plus rules) is planned for the security build | 🗓️ Deferred |
| F-009 | Security | SEC04-BP01 | 🟡 Low | Bedrock model invocation logging is not configured | By design ([BUILD_PLAN](BUILD_PLAN.md) D8): it records prompts and answers, so it belongs in the security build with its own retention and access controls | 🗓️ Deferred |
| F-005 | Security | SEC02-BP02 | 🟡 Low | The operator user has a long-lived access key | The key can only assume the deploy and review roles, both requiring MFA; alone it can read or change nothing. Rotated every 90 days; moves to IAM Identity Center later | ⚖️ Accepted risk |
| F-007 | Security | SEC08-BP02 | 🟡 Low | The alarm topic has no SSE, and logs and traces use default service encryption, not customer managed keys | The topic carries alarm state only, and logs carry metadata only. Customer managed keys cost $1/month each and are in the security build's scope | ⚖️ Accepted risk |
| F-011 | Operational Excellence | OPS11-BP01 | 🟡 Low | No Well-Architected Tool workload exists | This page and the re-assessments are the review record. A WA Tool workload is optional | Not applicable |
| F-012 | Security | SEC03-BP02 | 🟢 None | The function's role is least privilege (invoke only the configured models, write only its own log) and capped by a permissions boundary; only this API can invoke the function | - | Practice met |
| F-013 | Security | SEC03-BP02 | 🟢 None | Every method requires a Cognito token with the API scope and an API key; clients use client credentials only, with 60-minute tokens | - | Practice met |
| F-014 | Reliability | REL11-BP01 | 🟢 None | Alarms on 5xx errors, p95 latency, Lambda throttles and daily estimated cost notify a confirmed email subscription; the function is traced with X-Ray | - | Practice met |
| F-015 | Cost Optimization | COST03-BP05 | 🟢 None | Load and spend are bounded before compute: per-client throttle and daily quota, stage throttle, `max_tokens` cap, budget | - | Practice met |
| F-016 | Sustainability | SUS05-BP01 | 🟢 None | Arm64 serverless compute, a 6 KB package, no idle resources, 14-day log retention | - | Practice met |
| F-017 | Operational Excellence | OPS05-BP01 | 🟢 None | The whole workload is in Terraform and consistently tagged, with deploy, verify and remove runbooks and unit and integration tests | - | Practice met |

## Accepted risks & out of scope

| ID | Disposition | Why | Revisit |
|----|-------------|-----|---------|
| F-005 | Accepted risk | The operator key alone grants nothing; every action needs a role assumed with MFA | Rotate within 90 days of creation; replace with IAM Identity Center when the account setup moves to shared foundation code |
| F-007 | Accepted risk | No sensitive content is logged or published; customer managed keys add fixed cost | Security build |
| F-004 | Deferred | Authentication, throttling, quotas and validation cover this build's threat model | Security build |
| F-009 | Deferred | Prompt and answer capture needs its own privacy controls | Security build |
| F-011 | Not applicable | The review is recorded here and repeated as re-assessments | - |

Also out of scope for this build, and listed in [ARCHITECTURE.md](ARCHITECTURE.md#known-limitations-and-trade-offs): streaming, VPC endpoints and Bedrock Guardrails. Reserved concurrency on the function is now possible (the account limit is 1000) but not configured: the API Gateway throttles already cap the load before any function or model cost.

## Account context

These controls are account-wide and not created by this stack. In a shared account they belong to the account owner, so they are reported here for completeness and not counted in the workload scorecard. Anyone deploying this stack into their own account should enable them.

| ID | Best practice | Risk (account) | Observation | Recommendation |
|----|---------------|----------------|-------------|----------------|
| F-018 | SEC04-BP01 | 🔴 High | No CloudTrail trail, so there is no durable, tamper-evident record of API activity beyond the 90-day event history | Create one multi-region management-events trail to an encrypted S3 bucket with log file validation (the first copy of management events is free) |
| F-019 | SEC04-BP01 | 🟠 Medium | GuardDuty, Security Hub, AWS Config and IAM Access Analyzer are not enabled. Root MFA is on and the root user has no access keys | Enable GuardDuty and an account-level Access Analyzer at minimum; Security Hub and Config as budget allows |

## Review history

| Date | Type | Summary |
|------|------|---------|
| 2026-10-19 | A1 - workload review | All six pillars. 19 findings: 0 high, 3 medium, 3 low open; 6 practices met; 2 accepted risks; 4 deferred (2 of them account context); 1 not applicable |
| 2026-10-20 | A6 - re-assessment | Same scope and role. 5 findings remediated with new evidence (F-002, F-003, F-006, F-008, F-010); F-001 open pending an AWS quota increase; no regressions or new findings; accepted and deferred items re-confirmed. Open: 0 high, 1 medium, 0 low |
| 2026-10-28 | A6 - re-assessment | Same scope and role, after a fresh-clone rebuild of the stack. F-001 remediated with new evidence (account Lambda concurrency 1000, increase request closed); earlier fixes re-confirmed; no regressions or new findings; accepted and deferred items re-surfaced unchanged. Open: 0 high, 0 medium, 0 low |
