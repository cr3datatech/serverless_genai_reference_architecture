# Bootstrap IAM

One-time IAM setup, run by an account administrator before the first `terraform apply`. It creates a least-privilege operator identity that can deploy this stack and review it, without being able to touch anything else in the account or escalate its own permissions.

Designed to be safe in an **existing, shared account**: everything this stack creates is named `powerlab-*`, and the operator's rights stop there.

## What gets created

```
user/powerlab                         operator - can only assume the two control roles, and only with MFA
role/control/powerlab-deploy          deploys the stack            ← powerlab-deploy + powerlab-deploy-services
role/control/powerlab-review          Well-Architected review      ← AWS managed ReadOnlyAccess
policy/control/powerlab-deploy        core deploy permissions
policy/control/powerlab-deploy-services  feature additions (alarms, sign-in, model cost tags)
policy/control/powerlab-boundary      ceiling for every workload role Terraform creates
```

| File | Purpose |
|------|---------|
| `powerlab-deploy-policy.json` | Create/update/delete `powerlab-*` Lambda functions, API Gateway APIs, log groups, alarms, dashboards, IAM roles and policies; read and invoke Bedrock models; use the Terraform state bucket `powerlab-tfstate-*` |
| `powerlab-deploy-services-policy.json` | Additions for specific features: SNS topics `powerlab-*` for alarm emails; **one** Amazon Cognito user pool (the lab's, created by an administrator; `USER_POOL_ID` is filled in at create time) for client sign-in; Bedrock application inference profiles for per-stack model cost tracking. Kept separate because IAM caps a managed policy at 6,144 characters, and so each feature's permissions are easy to review |
| `powerlab-boundary-policy.json` | Permissions boundary - the most any workload role can ever do: write its own logs, traces and `PowerLab*` metrics, and invoke Bedrock models |
| `control-role-trust-policy.json` | Lets `user/powerlab` assume the control roles when signed in with MFA. `ACCOUNT_ID` is filled in at create time |
| `powerlab-user-policy.json` | The user's only permission: `sts:AssumeRole` into `role/control/powerlab-*` with MFA |

## How escalation is prevented

- **Boundary on every role.** The deploy role can only create or modify `role/powerlab-*` if the role carries `powerlab-boundary`. Even if a role is given `AdministratorAccess`, its effective permissions can't exceed the boundary.
- **Boundaries can't be removed.** `iam:DeleteRolePermissionsBoundary` is explicitly denied.
- **The control plane is out of reach.** The control roles and policies live under the IAM path `/control/`, which the `powerlab-*` patterns don't match, and an explicit deny blocks any IAM write or `PassRole` on them. The deploy role can't edit its own policy or the boundary.
- **`PassRole` only to Lambda and API Gateway**, and only for `powerlab-*` roles.
- **No long-lived deploy credentials.** The user's access key can do nothing except assume a role with MFA, and role sessions expire.

## Well-Architected alignment

This bootstrap is the **Security pillar** of the AWS Well-Architected Framework applied before any workload exists - identity and permissions are much harder to fix after resources depend on them.

| Control | Well-Architected practice it implements |
|---------|-----------------------------------------|
| Deploy and review run as **assumed roles** with expiring sessions | Use temporary credentials (`SEC02-BP02`) |
| **MFA** required to assume either role | Use strong sign-in mechanisms |
| Rights scoped to `powerlab-*` resources; review role is read-only | Grant least privilege access |
| Separate deploy and review identities | Separation of duties - the auditor can't change what it audits |
| **Permissions boundary** on every workload role | Establish permission guardrails; prevent privilege escalation |
| Policies validated with IAM Access Analyzer before use | Analyse and reduce permissions continuously |
| Everything defined as versioned JSON in this repo | Operational Excellence: infrastructure and policy as code |

**Known trade-off:** the operator is an IAM user with a long-lived access key, which a Well-Architected review will flag. The risk is mitigated because the key alone can do nothing (MFA is required for every role). The stronger alternative is IAM Identity Center, which issues only temporary credentials. See the [Learning Guide §4.4](../../docs/LEARNING_GUIDE.md#44-iam-least-privilege-and-permissions-boundaries).

## Setup, step by step

Run once, signed in to the AWS console as an administrator of the target account. Steps 1–5 run in **AWS CloudShell**, because the IAM console can't create roles and policies under the `/control/` path. Steps 6–8 are in the IAM console and on your own machine.

### 1. Open CloudShell

Click the terminal icon (`>_`) in the console's top bar. The selected region doesn't matter, because IAM is global.

### 2. Get the policy files

```bash
git clone <this-repo-url>
cd <repo-folder>/bootstrap/iam
ls    # four .json files and this README
```

### 3. Confirm the account

```bash
aws sts get-caller-identity
```

Check that `Account` is the account the stack should be deployed to.

### 4. Validate the policies

```bash
for f in powerlab-deploy-policy.json powerlab-deploy-services-policy.json powerlab-boundary-policy.json powerlab-user-policy.json; do
  echo "== $f"
  aws accessanalyzer validate-policy --policy-type IDENTITY_POLICY \
    --policy-document file://$f --query 'findings[].[findingType,issueCode,findingDetails]' --output text
done
```

Nothing printed under a file name means IAM Access Analyzer found no issues. Fix any `ERROR` or `SECURITY_WARNING` before going on. A `SUGGESTION` is advisory.

### 5. Create the policies, user and roles

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
TRUST=$(sed "s/ACCOUNT_ID/$ACCOUNT_ID/" control-role-trust-policy.json)

# Policies
aws iam create-policy --path /control/ --policy-name powerlab-boundary \
  --policy-document file://powerlab-boundary-policy.json
aws iam create-policy --path /control/ --policy-name powerlab-deploy \
  --policy-document file://powerlab-deploy-policy.json

# The lab's Cognito user pool, in the deployment region (see "Why the user pool is created here")
REGION=<deployment-region>
POOL_ID=$(aws cognito-idp create-user-pool --region "$REGION" --pool-name powerlab-clients --user-pool-tier LITE --deletion-protection ACTIVE --user-pool-tags Project=powerlab --query 'UserPool.Id' --output text)
echo "$POOL_ID"    # keep this - it goes in terraform.tfvars
aws iam create-policy --path /control/ --policy-name powerlab-deploy-services \
  --policy-document "$(sed "s/USER_POOL_ID/$POOL_ID/" powerlab-deploy-services-policy.json)"

# Operator user
aws iam create-user --user-name powerlab
aws iam put-user-policy --user-name powerlab --policy-name assume-control-roles \
  --policy-document file://powerlab-user-policy.json

# The trust policy names the new user; give IAM time to see it, or CreateRole
# fails with "MalformedPolicyDocument: Invalid principal"
aws iam wait user-exists --user-name powerlab && sleep 15

# Control roles
aws iam create-role --path /control/ --role-name powerlab-deploy \
  --assume-role-policy-document "$TRUST"
aws iam attach-role-policy --role-name powerlab-deploy \
  --policy-arn "arn:aws:iam::$ACCOUNT_ID:policy/control/powerlab-deploy"
aws iam attach-role-policy --role-name powerlab-deploy \
  --policy-arn "arn:aws:iam::$ACCOUNT_ID:policy/control/powerlab-deploy-services"

aws iam create-role --path /control/ --role-name powerlab-review \
  --assume-role-policy-document "$TRUST"
aws iam attach-role-policy --role-name powerlab-review \
  --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess
```

Check the result:

```bash
aws iam list-roles --path-prefix /control/ --query 'Roles[].Arn' --output text
aws iam list-policies --scope Local --path-prefix /control/ --query 'Policies[].Arn' --output text
```

Expect two roles (`powerlab-deploy`, `powerlab-review`) and three policies (`powerlab-boundary`, `powerlab-deploy`, `powerlab-deploy-services`).

### 6. Add MFA and an access key (IAM console)

1. **IAM → Users → powerlab → Security credentials.**
2. **Multi-factor authentication → Assign MFA device.** Pick an authenticator app, scan the QR code and enter two consecutive codes. Note the device ARN (`arn:aws:iam::<account-id>:mfa/<device-name>`) for step 7.
3. **Access keys → Create access key → Command Line Interface (CLI).** Copy the access key ID and secret now; the secret is shown only once. Don't paste them anywhere except step 7.

The user has no console password and doesn't need one.

### 7. Configure the CLI on your machine

Store the access key:

```bash
aws configure --profile powerlab
```

Then add the role profiles to `~/.aws/config` (local machine only - never commit it):

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

### 8. Test

```bash
aws sts get-caller-identity --profile powerlab-deploy   # prompts for an MFA code
aws sts get-caller-identity --profile powerlab-review
```

Each should return an `assumed-role/powerlab-deploy/...` or `assumed-role/powerlab-review/...` ARN. These are expected to fail:

```bash
aws iam list-users --profile powerlab                     # AccessDenied: the user alone can do nothing
aws iam delete-policy --profile powerlab-deploy \
  --policy-arn arn:aws:iam::<account-id>:policy/control/powerlab-boundary   # AccessDenied: control plane protected
```

## Before the first deploy

- **Bedrock model access.** Anthropic models need a one-time use-case form per account (Bedrock console → model catalog → pick a Claude model). An administrator may need to do this.
- **API Gateway CloudWatch role.** REST API logging uses one CloudWatch role for the whole account and region. The deploy role can read this setting but deliberately can't change it, so it doesn't overwrite a role other workloads rely on. If it isn't set yet, an administrator sets it once.
- **Terraform state bucket.** The deploy role can create and use a bucket named `powerlab-tfstate-<unique-suffix>`. The deploy steps cover this.

## Why the user pool is created here

Amazon Cognito doesn't support resource-tag conditions in IAM policies, and user pool ARNs contain generated IDs rather than names. So a deploy role can't be limited to "pools tagged `Project=powerlab`" or "pools named `powerlab-*`"; the only alternatives are *every* pool in the account, or *one specific* pool. In a shared account, every pool is too much.

So an administrator creates the lab's pool once, here, and the deploy policy names that pool's ID. The deploy role can manage what's *inside* that pool (the API scope, client apps, sign-in domain), which Terraform creates and destroys. It can't create other pools, touch any other pool, or delete this one. It's the same pattern as the IAM roles: shared foundations belong to the administrator, and the workload gets least-privilege access to them.

The pool uses the **Lite** feature tier, the cheapest one; machine-to-machine sign-in is billed per token issued regardless of tier.

## Updating an existing setup

When a later version of this repo changes the policies, an administrator applies the change in CloudShell after `git pull`. Validate first (step 4), then:

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# A policy that already exists: add a new version and make it the default.
# IAM keeps at most 5 versions - delete the oldest non-default one first if needed
# (aws iam list-policy-versions / delete-policy-version).
aws iam create-policy-version --set-as-default \
  --policy-arn "arn:aws:iam::$ACCOUNT_ID:policy/control/powerlab-deploy" \
  --policy-document file://powerlab-deploy-policy.json

# A policy that is new in this version: create it and attach it to the role.
# (powerlab-deploy-services first needs the lab user pool - see step 5.)
aws iam create-policy --path /control/ --policy-name powerlab-deploy-services \
  --policy-document "$(sed "s/USER_POOL_ID/$POOL_ID/" powerlab-deploy-services-policy.json)"
aws iam attach-role-policy --role-name powerlab-deploy \
  --policy-arn "arn:aws:iam::$ACCOUNT_ID:policy/control/powerlab-deploy-services"
```

**Why updates are an administrator task:** the deploy role is explicitly denied any change under `/control/`, so it can never widen its own permissions. Every permission increase is a deliberate, reviewed change made by someone else - separation of duties, a Well-Architected Security practice.

## Notes

- Every role Terraform creates in this repo sets `permissions_boundary` to `powerlab-boundary`; without it, `iam:CreateRole` is denied.
- The boundary will grow with later builds (for example `bedrock:ApplyGuardrail` for guardrails). Update `powerlab-boundary-policy.json` and run `aws iam create-policy-version --set-as-default` as an administrator.
- **Using IAM Identity Center instead:** create permission sets from `powerlab-deploy-policy.json` + `powerlab-deploy-services-policy.json` and `ReadOnlyAccess`, and skip the user, trust policy and profiles above. The boundary policy is still required.
