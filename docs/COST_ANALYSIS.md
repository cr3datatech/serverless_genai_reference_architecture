# Cost Analysis

What this stack costs, where the money goes, and how spend is limited and made visible. 🏛️ **Well-Architected, Cost Optimization:** *implement cloud financial management*, *adopt a consumption model*, *expenditure and usage awareness*.

**Prices checked:** October 2026, region `eu-west-1` (Europe, Ireland), USD, on-demand. AWS changes prices; check the linked pricing pages before relying on these figures, and update `price_per_mtok` in `terraform.tfvars` when model prices change.

## Summary

| | Cost |
|---|---|
| **Fixed, while deployed and idle** | About **$0.60 per month** (CloudWatch alarms) |
| **Per request** | Almost entirely the model's tokens: from about $0.00003 for a one-line Haiku answer to a few tenths of a cent for longer Sonnet or Opus answers |
| **After `terraform destroy`** | About **$0**: the state bucket (a few KB) and the bootstrap resources (IAM, an empty Cognito user pool, the budget) cost nothing or next to nothing |

## Model prices

The function calls Claude models through EU **geographic cross-region inference profiles** (`eu.` prefix), wrapped in application inference profiles. Application inference profiles themselves are free.

| Alias | Model | Input, $ per 1M tokens | Output, $ per 1M tokens |
|---|---|---|---|
| `fast` | Claude Haiku 4.5 | 1.00 | 5.00 |
| `balanced` | Claude Sonnet 4.6 | 3.00 | 15.00 |
| `best` | Claude Opus 4.6 | 5.00 | 25.00 |

These are the models' standard (global) list prices, as configured in `terraform.tfvars`. **Geographic profiles may cost more:** third-party price trackers report EU cross-region pricing at about 10% above global (for example $3.30 / $16.50 for Sonnet 4.6). That is not confirmed on the AWS pricing page, whose Anthropic tables load dynamically. Until it is, `cost_estimate_usd` may understate model cost by up to about 10%. Check the [Amazon Bedrock pricing page](https://aws.amazon.com/bedrock/pricing/) (Anthropic, Europe (Ireland), cross-region inference) and compare with the bill (below).

The 5.5 models the aliases are designed for ([PREFLIGHT_CHECKS 6.3](PREFLIGHT_CHECKS.md#63-enable-model-access)) have lower list prices: Haiku 5.5 $0.10 / $0.50, Sonnet 5.5 $2 / $10, Opus 5.5 $4 / $20 per 1M tokens.

### Measured per-request costs

From the deployed stack, as returned in `cost_estimate_usd`:

| Request | Alias | Tokens in / out | Estimated cost |
|---|---|---|---|
| "Reply with the single word: hello" | `fast` | 14 / 4 | $0.000034 |
| Same | `balanced` | 14 / 4 | $0.000102 |
| Same | `best` | 14 / 4 | $0.000170 |
| "Explain AWS Lambda in two sentences." | `balanced` | 15 / 71 | $0.001110 |
| Integration test run (`tests/test_integration.py`) | mixed | - | under $0.001 |

Output tokens cost five times as much as input tokens, so the length of the answer drives the cost. The `max_tokens` cap (1024 by default) bounds the most expensive possible answer: about $0.005 on `fast`, $0.015 on `balanced` and $0.026 on `best`.

## Everything else

| Service | What is billed | Price (approx.) | This stack |
|---|---|---|---|
| CloudWatch alarms | Per alarm metric per month | $0.10 | 5xx, latency and throttles alarms: 1 metric each. Daily cost alarm: 3 metrics (one per alias). **$0.60/month** |
| CloudWatch custom metrics | Per metric per month, pro-rated by the hours in which it receives data | $0.30 | 12 metrics (4 per alias). Pennies at lab usage; **$3.60/month** at most, if every alias is called every hour |
| CloudWatch Logs | Ingestion per GB; storage per GB-month | $0.57; $0.03 | About 1 KB per request, kept 14 days. Negligible |
| CloudWatch dashboard | Per dashboard per month | $3.00 | Off by default (`enable_dashboard`) |
| API Gateway REST API | Per million requests | $3.50 | Negligible at lab volumes |
| Lambda (arm64) | Per million requests; per GB-second | $0.20; $0.0000133 | 256 MB, about 1 second per call. Covered by the always-free allowance (1M requests and 400,000 GB-s per month) |
| Cognito | Per access token issued (machine-to-machine) | See [Cognito pricing](https://aws.amazon.com/cognito/pricing/) | One token per client per hour of use. Negligible |
| X-Ray | Per million traces recorded | $5.00 | First 100,000 traces per month are free |
| SNS | Email notifications | First 1,000 per month free | Alarm emails only |
| S3 (Terraform state) | Storage per GB-month | $0.023 | A few KB. Under $0.01 |
| IAM, inference profiles, budget | - | Free | - |

Arm64 (Graviton) Lambda is about 20% cheaper per GB-second than x86 (BUILD_PLAN D4).

## Cost by phase

| Phase | Adds | Fixed monthly cost |
|---|---|---|
| 0 - Prerequisites | IAM, Cognito user pool (no users), budget | $0 |
| 1 - Foundation | Lambda role, three application inference profiles, state bucket | Under $0.01 |
| 2 - Non-streaming API | Function, REST API, Cognito domain and app client, usage plan | $0 (pay per request) |
| 4 - Observability | Metrics, tracing, four alarms, SNS topic | About $0.60 (alarms), plus metrics while in use |
| Optional | Dashboard ($3), API access log (per GB) | Off by default |

## Scenarios

Monthly cost, assuming 500 input and 300 output tokens per request (a short question and a paragraph of answer).

| Scenario | Requests / month | `fast` (Haiku 4.5) | `balanced` (Sonnet 4.6) | Everything else |
|---|---|---|---|---|
| This lab: a few test sessions | ~200 | $0.40 | $1.20 | ~$0.60-1 |
| Small internal tool | 30,000 (1,000 a day) | $60 | $180 | ~$4-5 |
| Usage-plan maximum, one client | 15,000 (500 a day quota) | $30 | $90 | ~$4 |

The model is over 90% of the cost in every case, so the most effective savings are choosing the cheapest alias that does the job, keeping prompts and answers short, and the `max_tokens` cap.

## Spend controls

Several independent limits, so a single misconfiguration can't produce a runaway bill (BUILD_PLAN D9).

| Control | Limit | Where |
|---|---|---|
| Per-client quota | 500 requests per day | Usage plan (`client_throttle`) |
| Per-client and whole-API throttles | 2 and 5 requests per second | Usage plan, stage (`client_throttle`, `stage_throttle`) |
| Answer length | `max_tokens` capped at 1024 | Function (`max_tokens_cap`) |
| Request size | 64 KB | Function |
| Model allowlist | Only configured aliases can be called | Function and its IAM policy |
| Daily cost alarm | Email when estimated model cost exceeds $1 in a day | `alarms.daily_cost_usd` |
| Account budget | Email at 50%, 80% and 100% of $20 per month, and on forecast | [bootstrap/budget](../bootstrap/budget/README.md) |

The alarm and the budget complement each other: the alarm uses the function's own estimate and reacts within minutes; the budget uses actual charges, which arrive hours later but include everything.

## Checking estimates against the bill

1. **Activate the cost allocation tag** (administrator, once): Billing and Cost Management -> Cost allocation tags -> activate `Project`. Tags appear in Cost Explorer from activation onwards, after up to 24 hours.
2. **Cost Explorer:** filter by tag `Project = powerlab`, group by *Service*. Model charges appear under the Claude models' Marketplace listings, attributed through the tagged application inference profiles (BUILD_PLAN D13).
3. **Compare** with the `CostUSD` metric for the same days (CloudWatch -> Metrics -> `PowerLab/GenAIApi`, statistic Sum, period 1 day). A consistent gap of about 10% confirms the geographic profile premium: raise `price_per_mtok` in `terraform.tfvars` to match and apply.
