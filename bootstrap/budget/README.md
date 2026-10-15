# Bootstrap: Cost Guardrail (AWS Budget)

A one-time setup, run by an account administrator, that emails you before lab spending becomes a surprise. Do it before the first `terraform apply`.

This is the **Cost Optimization pillar** of the AWS Well-Architected Framework applied before anything is deployed: *implement cloud financial management* and *monitor cost and usage*, so that unexpected spend is caught in days rather than on the monthly bill.

## Why a budget, when the stack already has cost limits?

The stack itself limits spend with per-client quotas, a Lambda concurrency cap, a `max_tokens` cap and a cost alarm (see [BUILD_PLAN.md](../../docs/BUILD_PLAN.md) D9). Those limits live *inside* the stack, so a misconfiguration, a bug in the stack, or resources left running elsewhere can get past them. An AWS Budget sits *outside* the stack, at the billing level, and sees everything. Well-Architected favours independent layers of control, and this is the outermost one.

| Layer | Catches | Speed |
|-------|---------|-------|
| Usage plans, concurrency and token caps | Abuse or runaway clients of this API | Immediate (requests rejected) |
| In-stack cost alarm (EMF metrics) | Unusual model spend through this API | Minutes |
| **AWS Budget (this step)** | **Everything billed to the account**, including resources outside this stack | Hours (billing data refreshes several times a day) |

A budget **alerts**; it doesn't stop resources. Stopping is `terraform destroy`.

## What gets created

| Budget | Scope | Alerts |
|--------|-------|--------|
| `powerlab-account-monthly` | The whole account, all services | Email at 50%, 80% and 100% of actual spend, and when the month's **forecast** passes 100% |

**Why account-wide rather than tag-scoped?** Charges for third-party models on Amazon Bedrock (such as Claude) are billed through AWS Marketplace. By default they don't carry your resource tags, so a budget filtered on `Project=powerlab` would miss the largest cost. An account-wide budget catches it immediately. A lab-scoped budget can be added after the first deploy (see below).

**Choosing the amount:** in a dedicated lab account, use your lab allowance (for example `20`). In a shared account, use your normal monthly spend **plus** the lab allowance, so that only spend above the usual level triggers alerts. Check the normal spend in **Billing → Bills** or Cost Explorer.

**Cost of the budget itself:** AWS Budgets doesn't charge for your first two budgets.

## Setup

Run in **AWS CloudShell** as an administrator (the `powerlab-deploy` role deliberately has no billing permissions), from this folder:

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AMOUNT_USD=20                       # your monthly limit in USD
ALERT_EMAIL=you@example.com         # where alerts go

aws budgets create-budget --account-id "$ACCOUNT_ID" \
  --budget "$(sed "s/AMOUNT_USD/$AMOUNT_USD/" account-budget.json)" \
  --notifications-with-subscribers "$(sed "s/ALERT_EMAIL/$ALERT_EMAIL/g" notifications.json)"
```

Check it:

```bash
aws budgets describe-budget --account-id "$ACCOUNT_ID" --budget-name powerlab-account-monthly \
  --query 'Budget.[BudgetName,BudgetLimit.Amount,TimeUnit]' --output text
aws budgets describe-notifications-for-budget --account-id "$ACCOUNT_ID" \
  --budget-name powerlab-account-monthly --query 'Notifications[].[NotificationType,Threshold]' --output text
```

Expect the budget name with your amount and `MONTHLY`, followed by four notifications: `ACTUAL 50`, `ACTUAL 80`, `ACTUAL 100` and `FORECASTED 100`. The email address and amount are filled in at run time, so they never appear in this repository.

> **Note:** the forecast alert needs some spending history. On a quiet account it may not fire until there's enough data.

## After the first deploy: lab-scoped budget (optional)

Once the stack is deployed and making tagged Bedrock calls (see [BUILD_PLAN.md](../../docs/BUILD_PLAN.md), application inference profiles), you can add a budget that tracks only this lab:

1. **Billing → Cost allocation tags** → find `Project` under user-defined tags → **Activate**. A tag only appears here after a tagged resource exists, and activation takes up to 24 hours to take effect.
2. Create a second budget filtered on that tag:

```bash
aws budgets create-budget --account-id "$ACCOUNT_ID" \
  --budget '{"BudgetName":"powerlab-lab-monthly","BudgetLimit":{"Amount":"'"$AMOUNT_USD"'","Unit":"USD"},"TimeUnit":"MONTHLY","BudgetType":"COST","CostFilters":{"TagKeyValue":["user:Project$powerlab"]}}' \
  --notifications-with-subscribers "$(sed "s/ALERT_EMAIL/$ALERT_EMAIL/g" notifications.json)"
```

3. After a day of use, compare it with the account-wide budget in Cost Explorer (group by tag `Project`) to confirm that Bedrock charges are being attributed to the lab. If they aren't, keep relying on the account-wide budget.

## Removing it

```bash
aws budgets delete-budget --account-id "$ACCOUNT_ID" --budget-name powerlab-account-monthly
```
