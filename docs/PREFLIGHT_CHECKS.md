# Preflight Checks

A runbook of every command used to set up and verify the account before the first `terraform apply`. For each command it gives the **purpose**, the **expected response**, and **common errors** with their fixes.

Run the checks in order. Each one proves one assumption the deployment depends on, so a failure here is cheaper to fix than a failed `terraform apply`. In Well-Architected terms this is **Operational Excellence**: *understand your workload's readiness before you deploy, and make changes in small, verifiable steps*.

Placeholders in angle brackets (`<region>`, `<account-id>`, `<pool-id>`, `<haiku-profile-id>`) must be replaced with your own values. Don't commit those values: they belong in gitignored files or your own notes.

## Where to run each command

| Where | Identity | Used for |
|---|---|---|
| **AWS CloudShell** (in the console) | The administrator signed in to the console | Bootstrap: creating IAM policies, roles, the Cognito user pool and the budget |
| **Local terminal** | The `powerlab-deploy` or `powerlab-review` CLI profile (MFA prompt) | Everything the stack's operator does: verification, Terraform, testing |

The `powerlab-*` profiles exist only in `~/.aws/config` on the local machine; CloudShell doesn't have them (see check 2.1).

---

## 1. Tooling

### 1.1 AWS CLI version

| | |
|---|---|
| **Where** | Local terminal |
| **Command** | `aws --version` |
| **Purpose** | Confirms the CLI is recent enough. Several commands this project needs, including `aws bedrock list-inference-profiles`, don't exist in older 2.x releases |
| **Expected** | `aws-cli/2.x.x ...` from a 2025 or later release (for example `2.31` or higher) |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| A version such as `2.17.x` (mid-2024) | Old CLI | Upgrade. Windows: `winget upgrade --id Amazon.AWSCLI` (or `winget install --id Amazon.AWSCLI` if winget didn't install it originally), or run `msiexec.exe /i https://awscli.amazonaws.com/AWSCLIV2.msi`. macOS/Linux: see the [AWS CLI install guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html). Then **open a new terminal** |
| `aws.exe: error: argument operation: Invalid choice` on a Bedrock command | Same: the CLI predates that command | Upgrade as above |
| Old version still reported after upgrading | The terminal was opened before the upgrade | Close it and open a new one |
| Installer asks for an administrator password | Managed (work) machine | Ask IT, or run read-only checks in CloudShell in the meantime |

### 1.2 Terraform version

| | |
|---|---|
| **Where** | Local terminal |
| **Command** | `terraform version` |
| **Purpose** | The configuration requires Terraform 1.10 or later, for native S3 state locking (`use_lockfile`) |
| **Expected** | `Terraform v1.10.0` or later |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| Version below 1.10, or `Unsupported Terraform Core version` at `init` | Old Terraform | Upgrade with the tool that installed it. Chocolatey: `choco upgrade terraform -y` (administrator terminal). winget: `winget upgrade --id Hashicorp.Terraform`. Homebrew: `brew upgrade hashicorp/tap/terraform`. Otherwise download from [developer.hashicorp.com/terraform/install](https://developer.hashicorp.com/terraform/install). Then open a new terminal |
| `terraform` not recognised | Not installed or not on `PATH` | Install as above |
| `Unsupported argument ... use_lockfile` at `init` | Terraform older than 1.10 | Upgrade |

Updating Terraform doesn't change the AWS provider version: that is pinned separately in the committed `.terraform.lock.hcl`.

### 1.3 Node.js version

| | |
|---|---|
| **Where** | Local terminal |
| **Command** | `node --version` |
| **Purpose** | Builds the TypeScript Lambda function (from phase 2) |
| **Expected** | `v22.x` or later |
| **If missing or older** | Install the current LTS from [nodejs.org](https://nodejs.org), or `winget install OpenJS.NodeJS.LTS` / `choco install nodejs-lts` / `brew install node` |

---

## 2. Identity and roles

### 2.1 Deploy role works

| | |
|---|---|
| **Where** | Local terminal |
| **Command** | `aws sts get-caller-identity --profile powerlab-deploy --query Arn --output text` |
| **Purpose** | Proves the operator user can assume the deploy role with MFA: the access key, MFA device, trust policy and profile configuration all work together |
| **Expected** | Prompts for an MFA code, then prints `arn:aws:sts::<account-id>:assumed-role/powerlab-deploy/<session-name>` |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| `The config profile (powerlab-deploy) could not be found` | Running in CloudShell, or the profile isn't in the local `~/.aws/config` | Run locally; add the profile as described in [bootstrap/iam step 7](../bootstrap/iam/README.md#7-configure-the-cli-on-your-machine) |
| `AccessDenied ... not authorized to perform: sts:AssumeRole` | Wrong `role_arn` (often a missing `/control/` path), wrong `mfa_serial`, or the role's trust policy doesn't name the user | The role ARN must be `arn:aws:iam::<account-id>:role/control/powerlab-deploy`; copy the MFA identifier from IAM → Users → powerlab → Security credentials |
| `MultiFactorAuthentication failed with invalid MFA one time pass code` | Wrong or expired code | Wait for the next code; check the device clock |
| `InvalidClientTokenId` or `SignatureDoesNotMatch` | Wrong access key in the `powerlab` profile | `aws configure --profile powerlab` and re-enter the key |
| `ExpiredToken` | Cached role session has expired (sessions last about an hour) | Run the command again; it prompts for a new MFA code |

### 2.2 Review role works

| | |
|---|---|
| **Where** | Local terminal |
| **Command** | `aws sts get-caller-identity --profile powerlab-review --query Arn --output text` |
| **Purpose** | Proves the read-only role used for the Well-Architected review can be assumed |
| **Expected** | `arn:aws:sts::<account-id>:assumed-role/powerlab-review/<session-name>` |
| **Common errors** | Same as 2.1 |

### 2.3 The operator user alone can do nothing (negative test)

| | |
|---|---|
| **Where** | Local terminal |
| **Command** | `aws iam list-users --profile powerlab` |
| **Purpose** | Proves a leaked access key on its own is useless: the user's only permission is assuming roles with MFA |
| **Expected** | `AccessDenied ... because no identity-based policy allows the iam:ListUsers action` |
| **If it succeeds instead** | The user has extra policies attached. Remove everything except the `assume-control-roles` inline policy |

### 2.4 The deploy role can't weaken its own guardrails (negative test)

| | |
|---|---|
| **Where** | Local terminal |
| **Command** | `aws iam delete-policy --profile powerlab-deploy --policy-arn arn:aws:iam::<account-id>:policy/control/powerlab-boundary` |
| **Purpose** | Proves the explicit deny on `/control/` protects the permissions boundary from the role it constrains |
| **Expected** | `AccessDenied ... with an explicit deny in an identity-based policy` |
| **If it succeeds instead** | **Stop.** The boundary has been deleted and the protection isn't working; recreate the boundary and check the `ProtectControlPlaneIdentities` statement in the deploy policy |

### 2.5 Deploy role has both policies attached

| | |
|---|---|
| **Where** | CloudShell (administrator) |
| **Command** | `aws iam list-attached-role-policies --role-name powerlab-deploy --query 'AttachedPolicies[].PolicyName' --output text` |
| **Purpose** | Confirms the core and feature permissions are both attached |
| **Expected** | `powerlab-deploy	powerlab-deploy-services` |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| Only `powerlab-deploy` listed | The services policy was created but not attached | `aws iam attach-role-policy --role-name powerlab-deploy --policy-arn "arn:aws:iam::$ACCOUNT_ID:policy/control/powerlab-deploy-services"` |
| `NoSuchEntity ... role powerlab-deploy` | Role not created, or created without the `/control/` path | Re-run [bootstrap/iam step 5](../bootstrap/iam/README.md#5-create-the-policies-user-and-roles) |

### 2.6 Services policy names the right user pool

| | |
|---|---|
| **Where** | CloudShell (administrator) |
| **Command** | `aws iam get-policy-version --policy-arn "arn:aws:iam::$ACCOUNT_ID:policy/control/powerlab-deploy-services" --version-id $(aws iam get-policy --policy-arn "arn:aws:iam::$ACCOUNT_ID:policy/control/powerlab-deploy-services" --query 'Policy.DefaultVersionId' --output text) --query 'PolicyVersion.Document' --output json \| grep -E "userpool\|ResourceTag"` |
| **Purpose** | Confirms the active policy version grants access to exactly one Cognito user pool, the lab's |
| **Expected** | One line: `"Resource": "arn:aws:cognito-idp:*:*:userpool/<pool-id>"`, and no line containing `ResourceTag` |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| A line containing `ResourceTag` | An early version of the policy is active (Cognito doesn't support resource-tag conditions, so it grants nothing) | Add a corrected version: `aws iam create-policy-version --set-as-default --policy-arn "arn:aws:iam::$ACCOUNT_ID:policy/control/powerlab-deploy-services" --policy-document "$(sed "s/USER_POOL_ID/$POOL_ID/" powerlab-deploy-services-policy.json)"` |
| `userpool/USER_POOL_ID` (literal placeholder) | The policy was created without substituting the pool ID | Same fix, with `POOL_ID` set |
| `EntityAlreadyExists` when creating the policy | It was created on an earlier run | Use `create-policy-version` (above) rather than `create-policy` |
| `LimitExceeded` on `create-policy-version` | IAM keeps at most 5 versions | Delete the oldest non-default version: `aws iam delete-policy-version --policy-arn <arn> --version-id v1` |

---

## 3. Cognito user pool

### 3.1 Exactly one lab user pool exists

| | |
|---|---|
| **Where** | CloudShell (administrator) |
| **Command** | `aws cognito-idp list-user-pools --region <region> --max-results 20 --query "UserPools[?Name=='powerlab-clients'].[Id,CreationDate]" --output text` |
| **Purpose** | Confirms the pool created during bootstrap exists in the deployment region, and that there's only one |
| **Expected** | One line: `<pool-id>	<creation-date>` |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| Two or more lines | The create command was run more than once | Keep the pool named in the services policy (check 2.6) and delete the rest: `aws cognito-idp delete-user-pool --region <region> --user-pool-id <unused-pool-id>` |
| No lines | Pool created in another region (CloudShell defaults to the console's region) | Re-run the list with other regions; create pools with an explicit `--region` |
| `Unknown options: --user-pool-tier` at creation | Older CLI in that environment | Omit the option; the pool gets the default tier |

### 3.2 Recover the pool ID in a new shell session

| | |
|---|---|
| **Where** | CloudShell |
| **Command** | `POOL_ID=$(aws cognito-idp list-user-pools --region <region> --max-results 20 --query "UserPools[?Name=='powerlab-clients'].Id" --output text); echo "$POOL_ID"` |
| **Purpose** | Shell variables are lost when CloudShell restarts; this sets `POOL_ID` again |
| **Expected** | A single ID like `<region>_AbC123xyz` |

---

## 4. Budget

### 4.1 Budget amount

| | |
|---|---|
| **Where** | CloudShell (administrator) |
| **Command** | `aws budgets describe-budget --account-id "$ACCOUNT_ID" --budget-name powerlab-account-monthly --query 'Budget.[BudgetLimit.Amount,TimeUnit]' --output text` |
| **Purpose** | Confirms the monthly limit |
| **Expected** | `<amount>	MONTHLY`, for example `20.0	MONTHLY` |

### 4.2 Budget alerts

| | |
|---|---|
| **Where** | CloudShell (administrator) |
| **Command** | `aws budgets describe-notifications-for-budget --account-id "$ACCOUNT_ID" --budget-name powerlab-account-monthly --query 'Notifications[].[NotificationType,Threshold]' --output text` |
| **Purpose** | Confirms all four alerts exist |
| **Expected** | Four lines: `ACTUAL 50`, `ACTUAL 80`, `ACTUAL 100`, `FORECASTED 100` (in any order) |

### 4.3 Alert recipient

| | |
|---|---|
| **Where** | CloudShell (administrator) |
| **Command** | `aws budgets describe-subscribers-for-notification --account-id "$ACCOUNT_ID" --budget-name powerlab-account-monthly --notification NotificationType=ACTUAL,ComparisonOperator=GREATER_THAN,Threshold=50,ThresholdType=PERCENTAGE --query 'Subscribers[].Address' --output text` |
| **Purpose** | Confirms alerts go to a real mailbox |
| **Expected** | The intended alert email address |

**Common errors (section 4)**

| Symptom | Cause | Fix |
|---|---|---|
| `DuplicateRecordException ... the budget already exists` | Created on an earlier run | Use checks 4.1–4.3 to verify it instead of creating it again |
| Recipient is `you@example.com` | Created with the placeholder address | Delete and recreate: `aws budgets delete-budget --account-id "$ACCOUNT_ID" --budget-name powerlab-account-monthly`, then the create command from [bootstrap/budget](../bootstrap/budget/README.md#setup) with the real address |
| `NotFoundException` | Budget not created, or `ACCOUNT_ID` is empty | `ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)`, then create it |

---

## 5. API Gateway logging role

### 5.1 Account-level CloudWatch role

| | |
|---|---|
| **Where** | Local terminal |
| **Command** | `aws apigateway get-account --profile powerlab-deploy --region <region> --query cloudwatchRoleArn --output text` |
| **Purpose** | REST API logging needs one CloudWatch role per account **and region**. The deploy role can read this setting but deliberately can't change it, because it's shared by every API in the region |
| **Expected** | An IAM role ARN: the setting already exists and nothing more is needed |

**If it prints `None`**, an administrator sets it once in CloudShell:

| Step | Command |
|---|---|
| Create the role | `aws iam create-role --role-name apigateway-cloudwatch-logs --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"apigateway.amazonaws.com"},"Action":"sts:AssumeRole"}]}'` |
| Grant log permissions | `aws iam attach-role-policy --role-name apigateway-cloudwatch-logs --policy-arn arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs` |
| Register it with API Gateway | `aws apigateway update-account --region <region> --patch-operations op=replace,path=/cloudwatchRoleArn,value=arn:aws:iam::$ACCOUNT_ID:role/apigateway-cloudwatch-logs` |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| `BadRequestException: The role ARN does not have required permissions` on `update-account` | IAM changes take a few seconds to propagate | Wait 15 seconds and retry |
| An unfamiliar role ARN is returned | Another workload in the account already set it | Leave it; it works for all APIs in the region. Don't replace it |

---

## 6. Amazon Bedrock

### 6.1 Claude inference profiles available

| | |
|---|---|
| **Where** | Local terminal |
| **Command** | `aws bedrock list-inference-profiles --profile powerlab-deploy --region <region> --query "inferenceProfileSummaries[?contains(inferenceProfileId,'anthropic')].[inferenceProfileId,status]" --output text` |
| **Purpose** | Lists the Claude models reachable from the deployment region through cross-region inference profiles. These IDs are what the `fast` / `balanced` / `best` aliases map to in `terraform.tfvars` |
| **Expected** | Lines like `<geo>.anthropic.claude-<model>	ACTIVE`, where `<geo>` matches the region's geography (for example `eu`, `us`, `apac`) |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| `Invalid choice` | Old CLI | See check 1.1 |
| Empty output | No Claude profiles in this region, or the wrong region | Check `--region`; check the Bedrock console's model catalog for that region |
| `AccessDeniedException` | Deploy policy missing `bedrock:List*` | Check the `BedrockReadOnly` statement in the deploy policy |

### 6.2 One real model call

| | |
|---|---|
| **Where** | Local terminal (PowerShell 7 or Git Bash) |
| **Command** | `aws bedrock-runtime converse --profile powerlab-deploy --region <region> --model-id <haiku-profile-id> --messages '[{"role":"user","content":[{"text":"Reply with the single word: hello"}]}]' --query 'output.message.content[0].text' --output text` |
| **Purpose** | One call proves four things: the model is enabled for the account, the deploy role may invoke it, the inference profile routes correctly, and the profile ID is valid. Costs a fraction of a cent |
| **Expected** | `hello` (or a close variant) |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| `AccessDeniedException: ... don't have access to the model`, or `... <model> is not available for this account` | Model access isn't enabled for the account. This is an account-level gate, not IAM: third-party models need a one-time provider agreement (for Anthropic, a use-case form) and an AWS Marketplace subscription, **per model** | See [6.3](#63-enable-model-access) |
| `AccessDeniedException: ... not authorized to perform: bedrock:InvokeModel` | IAM, not model access | Check the `BedrockInvokeForTesting` statement covers both `foundation-model/*` and `inference-profile/*` |
| `ValidationException: Invocation of model ID ... with on-demand throughput isn't supported` | A bare model ID was used instead of an inference profile ID | Use an ID from check 6.1 (with the geographic prefix) |
| `ResourceNotFoundException` | Typo in the ID, or the profile isn't available in this region | Copy the ID exactly from check 6.1 |
| `ThrottlingException` | Account quota for that model reached | Wait and retry; persistent throttling means requesting a quota increase (Service Quotas → Amazon Bedrock) |
| PowerShell error about the `--messages` JSON | Older PowerShell versions strip the inner quotes | Run the same line in Git Bash, or upgrade to PowerShell 7.3+ |

Run check 6.2 once **for each model** used by an alias (`fast`, `balanced`, `best`). Access is granted per model, so one success doesn't prove the others.

### 6.3 Enable model access

| | |
|---|---|
| **Where** | AWS console (administrator), in the deployment region; the diagnosis command can run in CloudShell |
| **Diagnose** | `aws bedrock get-foundation-model-availability --region <region> --model-id anthropic.<model>` (the model ID is the inference profile ID without its geographic prefix, e.g. `anthropic.claude-haiku-5-5`) |
| **Purpose** | Shows which access requirement is missing: provider agreement, authorisation, Marketplace entitlement or regional availability |
| **Expected once enabled** | Every status is `AVAILABLE` or `AUTHORIZED` |

**Reading the diagnosis**

| Field | If not `AVAILABLE` / `AUTHORIZED` |
|---|---|
| `authorizationStatus` | The provider's use-case form hasn't been accepted: submit it in the console (steps below) |
| `agreementAvailability` | No model agreement has been accepted yet. If an offer exists (next table), accept it from the CLI |
| `entitlementAvailability` | The account can't subscribe to this model (account plan, organisation policy or billing); see *Common errors* |
| `regionAvailability` | The model isn't offered in this region; choose another region or model |

**Accept the agreement from the CLI** (administrator; CloudShell). Accepting subscribes the account to the model through AWS Marketplace at standard pay-per-token prices, with no upfront or monthly fee.

| Step | Command | Expected |
|---|---|---|
| Is there an offer? | `aws bedrock list-foundation-model-agreement-offers --region <region> --model-id anthropic.<model> --query 'offers[].offerId' --output text` | An offer ID such as `offer-...`. Empty means no offer: see *Common errors* |
| Accept the offers for every alias's model | `for m in <model-1> <model-2> <model-3>; do t=$(aws bedrock list-foundation-model-agreement-offers --region <region> --model-id anthropic.$m --query 'offers[0].offerToken' --output text); echo "== $m"; aws bedrock create-foundation-model-agreement --region <region> --model-id anthropic.$m --offer-token "$t" --output text; done` | The model ID echoed back for each model |
| Wait for activation | `for m in <model-1> <model-2> <model-3>; do echo "$m $(aws bedrock get-foundation-model-availability --region <region> --model-id anthropic.$m --query agreementAvailability.status --output text)"; done` | `PENDING`, then `AVAILABLE` within a few minutes |

**Or enable through the console**

1. Console region → the deployment region.
2. **Amazon Bedrock → Model catalog** → filter provider **Anthropic** → open the model.
3. If prompted for **use-case details**, submit the form. It is per account and covers that provider's models.
4. Open the model in the **Playground** and send one message. First use creates the AWS Marketplace subscription, which can take a few minutes to become active.
5. Repeat step 4 for every model an alias uses, then re-run check 6.2 for each.

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| Playground shows an access or subscription error | The account (or its AWS Organization) restricts Marketplace subscriptions, e.g. by an SCP | An organization administrator must allow `aws-marketplace:Subscribe` for the model |
| Still `not available for this account` after enabling | Subscription not yet active | Wait 5-15 minutes and retry |
| `not available for this account ... contact AWS Sales` although every diagnosis field is `AVAILABLE` / `AUTHORIZED`, while an older model from the same provider works | AWS restricts the newest models for some accounts (based on account history or billing type). Not fixable with IAM, agreements or the console | Open a support case (Account and billing, free on Basic support) asking for access to the named model in the region. Meanwhile map the alias to the newest model that works (check 6.2 per candidate), update `terraform.tfvars` and re-apply. The aliases exist so that clients are unaffected by this kind of change |
| `agreementAvailability: NOT_AVAILABLE` even after using the Playground | The Playground step didn't create the agreement | Accept the offer from the CLI (above) |
| `ConflictException` on `create-foundation-model-agreement` | The agreement already exists | Nothing to do; check the status |
| No offers listed for any model | The account isn't eligible: commonly an account on the AWS **Free plan** (which excludes third-party Marketplace models), an organisation policy blocking Marketplace, or a missing payment method | Upgrade to the Paid plan (Billing console), ask the organisation administrator, or add a payment method |
| `Unknown options` / `Invalid choice` for `get-foundation-model-availability` | Older CLI | Use the console steps; upgrade the CLI (check 1.1) |

---

## 7. CloudShell housekeeping

| Situation | Command / fix |
|---|---|
| Repository missing in CloudShell | CloudShell keeps a separate home folder per region. Switch the console to the region used before, or clone again: `git clone <this-repo-url>` |
| `git pull` refuses because of local changes | A file was edited in CloudShell. Discard it (the repository has the fix): `git checkout -- <file>`, then `git pull` |
| Stray file with a name like `iam attach-role-policy ...` | A multi-line paste was split wrongly and part of a command was taken as a filename. Preview with `git clean -n`, then remove with `git clean -f` |
| `InvalidInput: ARN arn:aws:iam::{ "UserId": ... }:policy/... is not valid` | `ACCOUNT_ID` holds the full JSON from `get-caller-identity` instead of the account number (the `--query Account --output text` part was left off). Reset it and check before use: `ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text); echo "$ACCOUNT_ID"` should print 12 digits only |
| `ACCOUNT_ID` or `POOL_ID` empty after a restart | Shell variables don't survive a CloudShell restart: `ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)`, and check 3.2 for the pool ID |
| `MalformedPolicyDocument: Invalid principal` on `create-role` | The role's trust policy names a user that IAM can't see yet (eventual consistency). Wait about 15 seconds and retry; the bootstrap steps include this wait |

## Checklist

| # | Check | Pass when |
|---|-------|-----------|
| 1.1 | CLI version | 2025 or later |
| 1.2 | Terraform version | 1.10 or later |
| 1.3 | Node.js version | 22 or later |
| 2.1 | Deploy role | `assumed-role/powerlab-deploy/...` |
| 2.2 | Review role | `assumed-role/powerlab-review/...` |
| 2.3 | User alone | `AccessDenied` |
| 2.4 | Boundary protected | `AccessDenied` (explicit deny) |
| 2.5 | Policies attached | `powerlab-deploy`, `powerlab-deploy-services` |
| 2.6 | Services policy | One `userpool/<pool-id>`, no `ResourceTag` |
| 3.1 | User pool | Exactly one `powerlab-clients` |
| 4.1–4.3 | Budget | Amount, four alerts, real recipient |
| 5.1 | API Gateway logging role | An ARN (or set once by an administrator) |
| 6.1 | Claude profiles | At least one `<geo>.anthropic...` `ACTIVE` |
| 6.2 | Model call | `hello`, for **each** alias's model |
| 6.3 | Model access | Enabled for every model an alias uses |

When every row passes, the account is ready for Phase 1 of the [build plan](BUILD_PLAN.md).
