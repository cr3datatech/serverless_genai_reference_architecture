# Well-Architected Review

This architecture is audited against the six pillars of the [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html), using the [Generative AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/generative-ai-lens.html) where it applies.

> **Status:** Not yet reviewed. The review runs once the stack is deployed.

## Method

- **Scope:** the resources this repo's Terraform deploys (API Gateway, Lambda, IAM, Bedrock access, CloudWatch, X-Ray), in a dedicated test account.
- **Approach:** a read-only, evidence-based assessment of the deployed workload. Every finding cites a Well-Architected best-practice ID and the configuration evidence behind it.
- **Cycle:** review → remediate → re-review. Remediated findings are kept below with their resolution, so the history stays visible.
- **What's published here:** pillar verdicts, findings and remediation status only. Account identifiers, resource ARNs and raw evidence are not published.

## Risk levels

| Level | Meaning |
|-------|---------|
| 🔴 **High (HRI)** | A plausible, near-term path to outage, breach, data loss, or material unplanned cost |
| 🟠 **Medium (MRI)** | Real risk, but mitigated, bounded, or dependent on another failure first |
| 🟡 **Low** | Best-practice deviation with limited practical impact |
| 🟢 **None** | Practice met - recorded to show it was checked |

## Scorecard

| Pillar | HRI | MRI | Low | Verdict |
|--------|-----|-----|-----|---------|
| Operational Excellence | – | – | – | Pending |
| Security | – | – | – | Pending |
| Reliability | – | – | – | Pending |
| Performance Efficiency | – | – | – | Pending |
| Cost Optimization | – | – | – | Pending |
| Sustainability | – | – | – | Pending |

## Findings

| ID | Pillar | Best practice | Risk | Finding | Remediation | Status |
|----|--------|---------------|------|---------|-------------|--------|
| – | – | – | – | – | – | – |

## Accepted risks & out of scope

_None recorded yet._

## Review history

| Date | Type | Summary |
|------|------|---------|
| – | – | – |
