# Bootstrap IAM

One-time IAM setup, run by an account administrator before the first `terraform apply`. It creates a least-privilege operator identity that can deploy this stack and review it, without being able to touch anything else in the account or escalate its own permissions.

Designed to be safe in an **existing, shared account**: everything this stack creates is named `powerlab-*`, and the operator's rights stop there.

## What gets created

```
user/powerlab                         operator — can only assume the two control roles, and only with MFA
role/control/powerlab-deploy          deploys the stack            ← powerlab-deploy-policy.json
role/control/powerlab-review          Well-Architected review      ← AWS managed ReadOnlyAccess
policy/control/powerlab-deploy        the deploy permissions
policy/control/powerlab-boundary      ceiling for every workload role Terraform creates
```

| File | Purpose |
|------|---------|
| `powerlab-deploy-policy.json` | Create/update/delete `powerlab-*` Lambda functions, API Gateway APIs, log groups, alarms, dashboards, IAM roles and policies; read and invoke Bedrock models; use the Terraform state bucket `powerlab-tfstate-*` |
| `powerlab-boundary-policy.json` | Permissions boundary — the most any workload role can ever do: write its own logs, traces and `PowerLab*` metrics, and invoke Bedrock models |
| `control-role-trust-policy.json` | Lets `user/powerlab` assume the control roles when signed in with MFA. `ACCOUNT_ID` is filled in at create time |
| `powerlab-user-policy.json` | The user's only permission: `sts:AssumeRole` into `role/control/powerlab-*` with MFA |

## How escalation is prevented

- **Boundary on every role.** The deploy role can only create or modify `role/powerlab-*` if the role carries `powerlab-boundary`. Even if a role is given `AdministratorAccess`, its effective permissions can't exceed the boundary.
- **Boundaries can't be removed.** `iam:DeleteRolePermissionsBoundary` is explicitly denied.
- **The control plane is out of reach.** The control roles and policies live under the IAM path `/control/`, which the `powerlab-*` patterns don't match, and an explicit deny blocks any IAM write or `PassRole` on them. The deploy role can't edit its own policy or the boundary.
- **`PassRole` only to Lambda and API Gateway**, and only for `powerlab-*` roles.
- **No long-lived deploy credentials.** The user's access key can do nothing except assume a role with MFA, and role sessions expire.

## Setup

Run as an administrator, from this folder, with Git Bash or any POSIX shell:

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
TRUST=$(sed "s/ACCOUNT_ID/$ACCOUNT_ID/" control-role-trust-policy.json)

# Policies
aws iam create-policy --path /control/ --policy-name powerlab-boundary \
  --policy-document file://powerlab-boundary-policy.json
aws iam create-policy --path /control/ --policy-name powerlab-deploy \
  --policy-document file://powerlab-deploy-policy.json

# Operator user (enable an MFA device for it in the console afterwards)
aws iam create-user --user-name powerlab
aws iam put-user-policy --user-name powerlab --policy-name assume-control-roles \
  --policy-document file://powerlab-user-policy.json

# Control roles
aws iam create-role --path /control/ --role-name powerlab-deploy \
  --assume-role-policy-document "$TRUST"
aws iam attach-role-policy --role-name powerlab-deploy \
  --policy-arn "arn:aws:iam::$ACCOUNT_ID:policy/control/powerlab-deploy"

aws iam create-role --path /control/ --role-name powerlab-review \
  --assume-role-policy-document "$TRUST"
aws iam attach-role-policy --role-name powerlab-review \
  --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess
```

Then, in the console: **IAM → Users → powerlab → Security credentials** — assign an MFA device and create one access key for the CLI.

## CLI profiles

Add to `~/.aws/config` (your local machine only — never commit it):

```ini
[profile powerlab]
region = <region>

[profile powerlab-deploy]
role_arn       = arn:aws:iam::<account-id>:role/control/powerlab-deploy
source_profile = powerlab
mfa_serial     = arn:aws:iam::<account-id>:mfa/<device-name>
region         = <region>

[profile powerlab-review]
role_arn       = arn:aws:iam::<account-id>:role/control/powerlab-review
source_profile = powerlab
mfa_serial     = arn:aws:iam::<account-id>:mfa/<device-name>
region         = <region>
```

Store the access key under `[powerlab]` with `aws configure --profile powerlab`. Check it works:

```bash
aws sts get-caller-identity --profile powerlab-deploy   # prompts for an MFA code
```

## Before the first deploy

- **Bedrock model access.** Anthropic models need a one-time use-case form per account (Bedrock console → model catalog → pick a Claude model). An administrator may need to do this.
- **API Gateway CloudWatch role.** REST API logging uses one CloudWatch role for the whole account and region. The deploy role can read this setting but deliberately can't change it, so it doesn't overwrite a role other workloads rely on. If it isn't set yet, an administrator sets it once.
- **Terraform state bucket.** The deploy role can create and use a bucket named `powerlab-tfstate-<unique-suffix>`. The deploy steps cover this.

## Notes

- Every role Terraform creates in this repo sets `permissions_boundary` to `powerlab-boundary`; without it, `iam:CreateRole` is denied.
- The boundary will grow with later builds (for example `bedrock:ApplyGuardrail` for guardrails). Update `powerlab-boundary-policy.json` and run `aws iam create-policy-version --set-as-default` as an administrator.
- **Using IAM Identity Center instead:** create permission sets from `powerlab-deploy-policy.json` and `ReadOnlyAccess`, and skip the user, trust policy and profiles above. The boundary policy is still required.
