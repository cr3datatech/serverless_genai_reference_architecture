# Deployment

How to deploy, verify and remove the stack. Run the [preflight checks](PREFLIGHT_CHECKS.md) first; every command here assumes they pass.

Each step lists the **command**, its **purpose**, the **expected result** and **common errors**. Placeholders in angle brackets must be replaced with your own values.

**Where to run the commands:** a **local terminal** (not CloudShell), in the **repository root**, and in the **same terminal window** throughout. The credentials loaded in step 2 exist only in that window.

**About `terraform -chdir=terraform`:** Terraform reads the `.tf` files in its working directory, and this project keeps them in the `terraform/` subfolder. `-chdir=terraform` runs the command as if from inside that folder, so AWS CLI and Terraform commands can all run from the repository root. Equivalently, `cd terraform` once and drop the `-chdir=terraform` part (`terraform init "-backend-config=backend.hcl"`, `terraform plan -out=tfplan`, ...). Either way, `backend.hcl` and `tfplan` are read from and written to `terraform/`.

🏛️ **Well-Architected:** deployment is fully automated, repeatable and reversible (**Operational Excellence**: *perform operations as code*, *make frequent, small, reversible changes*). Credentials are temporary and MFA-backed (**Security**). Teardown is one command, so nothing is left running and billing (**Cost Optimization**, **Sustainability**).

## Current scope

| Phase | Creates | Status |
|---|---|---|
| 1 - Foundation | Lambda execution role (with permissions boundary); one tagged Bedrock application inference profile per model alias | Available |
| 2 - Non-streaming path | Lambda function, REST API, API key, usage plan, Cognito authorizer | Planned |
| 3 onward | See [BUILD_PLAN.md](BUILD_PLAN.md) | Planned |

---

## One-time setup

### 1. Create the configuration files

| | |
|---|---|
| **Commands** | `cp terraform/terraform.tfvars.example terraform/terraform.tfvars` and `cp terraform/backend.hcl.example terraform/backend.hcl` |
| **Purpose** | Account-specific settings live in these two files, which are gitignored |
| **Then edit** | `terraform.tfvars`: the region and the inference profile IDs from [preflight check 6.1](PREFLIGHT_CHECKS.md#61-claude-inference-profiles-available). `backend.hcl`: the region and a state bucket name `powerlab-tfstate-<unique-suffix>` (bucket names are global, so add a random suffix, e.g. 8 hex characters) |
| **Check** | `git status` must **not** list either file. If it does, `.gitignore` is missing an entry; don't commit them |

### 2. Load deploy credentials into the shell

Terraform can't prompt for an MFA code, so the AWS CLI performs the MFA sign-in and hands Terraform the resulting temporary credentials as environment variables.

| | |
|---|---|
| **Command (PowerShell)** | `aws configure export-credentials --profile powerlab-deploy --format powershell \| Invoke-Expression` |
| **Command (Bash / Git Bash)** | `eval "$(aws configure export-credentials --profile powerlab-deploy --format env)"` |
| **Purpose** | Sets `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_SESSION_TOKEN` for this terminal only. Nothing is written to disk |
| **Expected** | An MFA prompt (unless a cached session is still valid), then no output |
| **Check** | `aws sts get-caller-identity --query Arn --output text` (no `--profile`) prints `...assumed-role/powerlab-deploy/...` |

**Why not just set `AWS_PROFILE`?** Setting `$env:AWS_PROFILE = "powerlab-deploy"` (PowerShell) or `export AWS_PROFILE=powerlab-deploy` (Bash) makes the AWS CLI use that profile without `--profile`, which is fine for CLI commands. Terraform, however, can't display the MFA prompt the profile requires and fails. Exporting credentials works for both the CLI and Terraform. To undo `AWS_PROFILE`: `Remove-Item Env:AWS_PROFILE` (PowerShell) or `unset AWS_PROFILE` (Bash). Don't set it to the bare `powerlab` profile: that identity can only assume roles, so every other command returns `AccessDenied`.

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| `aws: error: argument command: Invalid choice ... export-credentials` | AWS CLI too old | Upgrade (see [preflight check 1.1](PREFLIGHT_CHECKS.md#11-aws-cli-version)) |
| Later Terraform commands fail with `ExpiredToken` | The temporary credentials last about an hour | Run this step again |
| `get-caller-identity` shows a different identity | Other credentials set in the environment or a default profile | Open a fresh terminal and repeat this step |

### 3. Create the Terraform state bucket

Run once per account. The deploy role may only create buckets named `powerlab-tfstate-*`.

| Step | Command |
|---|---|
| Create | `aws s3api create-bucket --bucket <state-bucket> --region <region> --create-bucket-configuration LocationConstraint=<region>` |
| Versioning (recover earlier states) | `aws s3api put-bucket-versioning --bucket <state-bucket> --versioning-configuration Status=Enabled` |
| Block all public access | `aws s3api put-public-access-block --bucket <state-bucket> --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true` |
| Tag | `aws s3api put-bucket-tagging --bucket <state-bucket> --tagging 'TagSet=[{Key=Project,Value=powerlab},{Key=ManagedBy,Value=cli}]'` |
| Verify | `aws s3api get-bucket-versioning --bucket <state-bucket> --query Status --output text` |

| | |
|---|---|
| **Purpose** | Terraform's state file records every resource it manages. Keeping it in a versioned, private, encrypted bucket means it's shared, recoverable, and never committed to git. Objects are encrypted by default (SSE-S3), so no extra encryption step is needed |
| **Expected** | `create-bucket` prints a `Location`; the verify command prints `Enabled`; the other commands print nothing |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| `BucketAlreadyExists` | The name is taken by another AWS account (names are global) | Choose a different suffix; update `backend.hcl` |
| `BucketAlreadyOwnedByYou` | Already created on an earlier run | Carry on with the remaining commands |
| `AccessDenied` on `CreateBucket` | Name doesn't start with `powerlab-tfstate-`, or credentials from step 2 aren't loaded | Fix the name, or repeat step 2 |
| `IllegalLocationConstraintException` | `--region` and `LocationConstraint` differ | Use the same region in both |

### 4. Initialise Terraform

| | |
|---|---|
| **Command** | `terraform -chdir=terraform init "-backend-config=backend.hcl"` |
| **Purpose** | Downloads the AWS provider (versions pinned by the committed `.terraform.lock.hcl`) and connects to the state bucket |
| **Expected** | `Terraform has been successfully initialized!` |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| `No positional arguments are expected` | Windows PowerShell 5.1 splits unquoted arguments that start with `-` and contain a `.`, so `-backend-config=backend.hcl` becomes `-backend-config=backend` plus `.hcl` | Keep the quotes: `"-backend-config=backend.hcl"`. PowerShell 7 (`winget install Microsoft.PowerShell`) doesn't have this behaviour |
| `No valid credential sources found` | Step 2 not run in this terminal | Run step 2 |
| `AccessDenied` / `403` on the bucket | Bucket name in `backend.hcl` doesn't match the one created, or a different identity | Compare names; check identity (step 2 check) |
| `the given checksum does not match` | Lock file and provider download disagree (e.g. a new platform) | `terraform -chdir=terraform providers lock -platform=<os_arch>` and commit the updated lock file |

---

## Deploy

### 5. Plan

| | |
|---|---|
| **Command** | `terraform -chdir=terraform plan -out=tfplan` |
| **Purpose** | Shows exactly what will be created, changed or destroyed, without changing anything. Saving the plan guarantees that what is applied is what was reviewed |
| **Expected (phase 1)** | `Plan: 5 to add, 0 to change, 0 to destroy.` (one IAM role, one inline role policy, three application inference profiles) |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| `reading Bedrock Inference Profile (...): ResourceNotFoundException` | A profile ID in `terraform.tfvars` doesn't exist in this region | Copy IDs exactly from [preflight check 6.1](PREFLIGHT_CHECKS.md#61-claude-inference-profiles-available) |
| `ExpiredToken` | Credentials from step 2 expired | Repeat step 2 |

### 6. Apply

| | |
|---|---|
| **Command** | `terraform -chdir=terraform apply tfplan` |
| **Purpose** | Creates exactly what the saved plan showed |
| **Expected** | `Apply complete! Resources: 5 added, 0 changed, 0 destroyed.` followed by the outputs `lambda_role_arn` and `model_aliases` |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| `AccessDenied ... iam:CreateRole` | The role would be created without the permissions boundary, or the boundary name differs from `permissions_boundary_name` | The boundary must be `policy/control/powerlab-boundary` (bootstrap/iam). This error means the guardrail is working |
| `AccessDenied ... bedrock:CreateInferenceProfile` | `powerlab-deploy-services` policy not attached | [Preflight check 2.5](PREFLIGHT_CHECKS.md#25-deploy-role-has-both-policies-attached) |
| `Saved plan is stale` | Something changed after planning | Run step 5 again |

---

## Verify

### 7. The Lambda role carries the boundary

| | |
|---|---|
| **Command** | `aws iam get-role --role-name powerlab-genai-api-lambda --query 'Role.PermissionsBoundary.PermissionsBoundaryArn' --output text` |
| **Purpose** | Confirms the workload role is capped by the boundary |
| **Expected** | `arn:aws:iam::<account-id>:policy/control/powerlab-boundary` |

### 8. The application inference profiles exist and are tagged

| | |
|---|---|
| **Command** | `aws bedrock list-inference-profiles --region <region> --type-equals APPLICATION --query "inferenceProfileSummaries[].[inferenceProfileName,status]" --output text` |
| **Purpose** | Confirms one profile per alias |
| **Expected** | `powerlab-genai-api-fast`, `powerlab-genai-api-balanced`, `powerlab-genai-api-best`, each `ACTIVE` |

### 9. A model call through an application profile

| | |
|---|---|
| **Command** | `aws bedrock-runtime converse --region <region> --model-id <fast-profile-arn> --messages '[{"role":"user","content":[{"text":"Reply with the single word: hello"}]}]' --query 'output.message.content[0].text' --output text` |
| **Purpose** | Proves the tagged profile works end to end. `<fast-profile-arn>` is the `fast` entry of `terraform -chdir=terraform output model_aliases` |
| **Expected** | `hello` |
| **Common errors** | As [preflight check 6.2](PREFLIGHT_CHECKS.md#62-one-real-model-call). In PowerShell versions before 7.3, run it in Git Bash if the JSON is rejected |

---

## Remove

### 10. Destroy the stack

| | |
|---|---|
| **Command** | `terraform -chdir=terraform destroy` |
| **Purpose** | Removes everything Terraform created. Run it between work sessions: the stack rebuilds in minutes and nothing bills while it's gone |
| **Expected** | A plan listing every resource to destroy, a `yes` confirmation, then `Destroy complete!` |
| **Not removed** | The state bucket and everything from `bootstrap/` (IAM, Cognito user pool, budget). These are account foundations shared by deployments |
