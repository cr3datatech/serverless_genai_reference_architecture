# Deployment

How to deploy, verify and remove the stack. Run the [preflight checks](PREFLIGHT_CHECKS.md) first; every command here assumes they pass.

Each step lists the **command**, its **purpose**, the **expected result** and **common errors**. Placeholders in angle brackets must be replaced with your own values.

**Where to run the commands:** a **local terminal** (not CloudShell), in the **repository root**, and in the **same terminal window** throughout. The credentials loaded in step 2 exist only in that window.

**About `terraform -chdir=terraform`:** Terraform reads the `.tf` files in its working directory, and this project keeps them in the `terraform/` subfolder. `-chdir=terraform` runs the command as if from inside that folder, so AWS CLI and Terraform commands can all run from the repository root. Equivalently, `cd terraform` once and drop the `-chdir=terraform` part (`terraform init "-backend-config=backend.hcl"`, `terraform plan -out=tfplan`, ...). Either way, `backend.hcl` and `tfplan` are read from and written to `terraform/`.

🏛️ **Well-Architected:** deployment is fully automated, repeatable and reversible (**Operational Excellence**: *perform operations as code*, *make frequent, small, reversible changes*). Credentials are temporary and MFA-backed (**Security**). Teardown is one command, so nothing is left running and billing (**Cost Optimization**, **Sustainability**).

## Current scope

| Phase | Creates | Status |
|---|---|---|
| 1 - Foundation | Lambda execution role (with permissions boundary); one tagged Bedrock application inference profile per model alias | Deployed |
| 2 - Non-streaming path | Lambda function and log group; REST API (`POST /v1/chat`, `GET /v1/models`) with Cognito authorizer, API keys, usage plan and stage throttling; Cognito domain, resource server and one app client per API client | Deployed |
| 3 onward | See [BUILD_PLAN.md](BUILD_PLAN.md) | Planned |

---

## One-time setup

### 1. Create the configuration files

| | |
|---|---|
| **Commands** | `cp terraform/terraform.tfvars.example terraform/terraform.tfvars` and `cp terraform/backend.hcl.example terraform/backend.hcl` |
| **Purpose** | Account-specific settings live in these two files, which are gitignored |
| **Then edit** | `terraform.tfvars`: the region, the inference profile IDs from [preflight check 6.1](PREFLIGHT_CHECKS.md#61-claude-inference-profiles-available) and their prices, and the user pool ID from [preflight check 3.1](PREFLIGHT_CHECKS.md#31-exactly-one-lab-user-pool-exists). `backend.hcl`: the region and a state bucket name `powerlab-tfstate-<unique-suffix>` (bucket names are global, so add a random suffix, e.g. 8 hex characters) |
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

### 5. Build the function

| | |
|---|---|
| **Commands** | `npm --prefix lambda ci` then `npm --prefix lambda test` then `npm --prefix lambda run build` |
| **Purpose** | Installs the exact dependency versions from `lambda/package-lock.json`, type-checks and runs the unit tests (request validation, cost estimate, error mapping; no AWS calls), then compiles `lambda/src/*.ts` to `lambda/dist/*.js`. Terraform zips `lambda/dist` and redeploys the function whenever it changes |
| **Expected** | `pass 6`, `fail 0`, then no output from the build; `lambda/dist` holds `index.js`, `chat.js`, `config.js` and `http.js` (about 12 KB in total) |

**Why plain compiled JavaScript, not a bundle:** the function's only runtime dependency is the AWS SDK, which the Lambda Node.js runtime already provides. So the TypeScript compiler's output is deployed as is: one `.js` file per source file, with the comments kept. It reads almost line for line like `lambda/src`, so the code can be followed in the Lambda console (**Operational Excellence**: code that operators can read), and the package stays tiny, which keeps cold starts fast (**Performance Efficiency**). The trade-off is that AWS controls the SDK version at runtime; the version used for type-checking and tests is pinned in `package.json`. If a later build adds other dependencies, bundling (for example with esbuild, already used for the tests) becomes necessary.

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| `npm: command not found` | Node.js not installed | Install Node.js 22 or later ([preflight check 1.3](PREFLIGHT_CHECKS.md#13-nodejs-version)) |
| Plan: `error archiving directory: could not archive missing directory` | This step was skipped, so `lambda/dist` doesn't exist | Run the build, then plan again |
| Apply: `CreateFunction, decomposing request: bufio.Scanner: token too long` | The inline upload is too large for the provider's request handling (seen with a 578 KB package that bundled the AWS SDK) | Don't bundle the AWS SDK into the package; the runtime provides it |

### 6. Plan

| | |
|---|---|
| **Command** | `terraform -chdir=terraform plan -out=tfplan` |
| **Purpose** | Shows exactly what will be created, changed or destroyed, without changing anything. Saving the plan guarantees that what is applied is what was reviewed |
| **Expected (first deploy)** | `Plan: 29 to add, 0 to change, 0 to destroy.` with the default single API client (5 resources for phase 1, 24 for phase 2) |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| `reading Bedrock Inference Profile (...): ResourceNotFoundException` | A profile ID in `terraform.tfvars` doesn't exist in this region | Copy IDs exactly from [preflight check 6.1](PREFLIGHT_CHECKS.md#61-claude-inference-profiles-available) |
| `No value for required variable "cognito_user_pool_id"` | `terraform.tfvars` predates phase 2 | Add `cognito_user_pool_id` (see `terraform.tfvars.example`) |
| `ExpiredToken` | Credentials from step 2 expired | Repeat step 2 |

### 7. Apply

| | |
|---|---|
| **Command** | `terraform -chdir=terraform apply tfplan` |
| **Purpose** | Creates exactly what the saved plan showed |
| **Expected** | `Apply complete!` followed by the outputs `api_url`, `token_url`, `oauth_scope`, `client_ids`, `model_aliases` and `lambda_role_arn`, with `client_secrets` and `api_keys` shown as `<sensitive>` |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| `AccessDenied ... iam:CreateRole` | The role would be created without the permissions boundary, or the boundary name differs from `permissions_boundary_name` | The boundary must be `policy/control/powerlab-boundary` (bootstrap/iam). This error means the guardrail is working |
| `AccessDenied ... bedrock:CreateInferenceProfile` | `powerlab-deploy-services` policy not attached | [Preflight check 2.5](PREFLIGHT_CHECKS.md#25-deploy-role-has-both-policies-attached) |
| `AccessDenied ... cognito-idp:...` | `cognito_user_pool_id` differs from the pool named in the `powerlab-deploy-services` policy | Use the pool created in bootstrap; the deploy role may manage only that one ([preflight check 2.6](PREFLIGHT_CHECKS.md#26-services-policy-names-the-right-user-pool)) |
| `Domain already exists` on the Cognito domain | Another account uses the same prefix in this region | Change the prefix in `cognito.tf`; it must be unique per region |
| `ValidationException: Value at 'description' failed to satisfy constraint: ... ([0-9a-zA-Z:.][ _-]?)+` | Bedrock inference profile descriptions allow only letters, digits, `:` and `.`, separated by single spaces, `_` or `-` (no quotes, arrows or other punctuation) | Fixed in `bedrock.tf`; if you customise descriptions, keep to that pattern |
| `Saved plan is stale` | Something changed after planning | Run step 6 again |
| Some resources created, others failed | Terraform applies what it can and records it in state | Fix the cause, then plan and apply again: Terraform creates only what's missing. A failed apply never needs manual cleanup first |

---

## Verify

### 8. The Lambda role carries the boundary

| | |
|---|---|
| **Command** | `aws iam get-role --role-name powerlab-genai-api-lambda --query 'Role.PermissionsBoundary.PermissionsBoundaryArn' --output text` |
| **Purpose** | Confirms the workload role is capped by the boundary |
| **Expected** | `arn:aws:iam::<account-id>:policy/control/powerlab-boundary` |

### 9. The application inference profiles exist and are tagged

| | |
|---|---|
| **Command** | `aws bedrock list-inference-profiles --region <region> --type-equals APPLICATION --query "inferenceProfileSummaries[].[inferenceProfileName,status]" --output text` |
| **Purpose** | Confirms one profile per alias |
| **Expected** | `powerlab-genai-api-fast`, `powerlab-genai-api-balanced`, `powerlab-genai-api-best`, each `ACTIVE` |

### 10. A model call through an application profile

| | |
|---|---|
| **Command** | `aws bedrock-runtime converse --region <region> --model-id <fast-profile-arn> --messages '[{"role":"user","content":[{"text":"Reply with the single word: hello"}]}]' --query 'output.message.content[0].text' --output text` |
| **Purpose** | Proves the tagged profile works on its own, before the API is involved. `<fast-profile-arn>` is the `fast` entry of `terraform -chdir=terraform output model_aliases` |
| **Expected** | `hello` |
| **Common errors** | As [preflight check 6.2](PREFLIGHT_CHECKS.md#62-one-real-model-call). `AccessDeniedException ... bedrock:InvokeModel on resource ...application-inference-profile/...` means the account's `powerlab-deploy` policy predates application-profile support: apply the current `powerlab-deploy-policy.json` as a new policy version ([bootstrap/iam: Updating an existing setup](../bootstrap/iam/README.md#updating-an-existing-setup)). In PowerShell versions before 7.3, run it in Git Bash if the JSON is rejected |

### 11. Get an access token

A client proves who it is with the OAuth 2.0 **client-credentials** flow: it sends its client ID and secret to the Cognito token endpoint and receives an access token valid for 60 minutes. These commands keep the secret, the API key and the token in shell variables; don't paste them into files or tickets.

| | |
|---|---|
| **Commands (Bash / Git Bash)** | `API=$(terraform -chdir=terraform output -raw api_url); TOKEN_URL=$(terraform -chdir=terraform output -raw token_url); SCOPE=$(terraform -chdir=terraform output -raw oauth_scope)` then `CID=$(terraform -chdir=terraform output -json client_ids \| python -c "import sys,json;print(json.load(sys.stdin)['demo'])"); CSEC=$(terraform -chdir=terraform output -json client_secrets \| python -c "import sys,json;print(json.load(sys.stdin)['demo'])"); KEY=$(terraform -chdir=terraform output -json api_keys \| python -c "import sys,json;print(json.load(sys.stdin)['demo'])")` then `TOKEN=$(curl -s -d "grant_type=client_credentials&scope=$SCOPE&client_id=$CID&client_secret=$CSEC" "$TOKEN_URL" \| python -c "import sys,json;print(json.load(sys.stdin)['access_token'])"); echo ${#TOKEN}` |
| **Commands (PowerShell)** | `$api = terraform -chdir=terraform output -raw api_url; $tokenUrl = terraform -chdir=terraform output -raw token_url; $scope = terraform -chdir=terraform output -raw oauth_scope` then `$cid = (terraform -chdir=terraform output -json client_ids \| ConvertFrom-Json).demo; $csec = (terraform -chdir=terraform output -json client_secrets \| ConvertFrom-Json).demo; $key = (terraform -chdir=terraform output -json api_keys \| ConvertFrom-Json).demo` then `$token = (Invoke-RestMethod -Method Post -Uri $tokenUrl -Body @{grant_type='client_credentials'; scope=$scope; client_id=$cid; client_secret=$csec}).access_token; $token.Length` |
| **Purpose** | Reads the endpoints and the `demo` client's credentials from Terraform, then requests a token |
| **Expected** | A number around 800-900: the token's length (the token itself isn't printed) |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| `invalid_client` | Wrong client ID or secret | Read them again from the Terraform outputs |
| `invalid_scope` or `unauthorized_client` | Scope doesn't match `oauth_scope`, or the app client doesn't allow the client-credentials flow | Use the `oauth_scope` output; check `cognito.tf` |
| `Could not resolve host` | The Cognito domain was created moments ago | Wait a minute and retry |

### 12. Call the API

| | |
|---|---|
| **Commands (Bash / Git Bash)** | `curl -s -H "Authorization: Bearer $TOKEN" -H "x-api-key: $KEY" "$API/v1/models"` and `curl -s -H "Authorization: Bearer $TOKEN" -H "x-api-key: $KEY" -H "content-type: application/json" -d '{"model":"fast","messages":[{"role":"user","content":"Reply with the single word: hello"}]}' "$API/v1/chat"` |
| **Commands (PowerShell)** | `$h = @{Authorization="Bearer $token"; 'x-api-key'=$key}` then `Invoke-RestMethod -Uri "$api/v1/models" -Headers $h` and `Invoke-RestMethod -Method Post -Uri "$api/v1/chat" -Headers $h -ContentType 'application/json' -Body '{"model":"fast","messages":[{"role":"user","content":"Reply with the single word: hello"}]}'` |
| **Purpose** | Exercises the full path: token check, API key and usage plan, function, application inference profile, model |
| **Expected (models)** | `{"data":[{"id":"balanced",...},{"id":"best",...},{"id":"fast",...,"default":true}]}` |
| **Expected (chat)** | `{"output":"hello","stop_reason":"end_turn","usage":{"input_tokens":14,"output_tokens":4},"cost_estimate_usd":0.000034,"model":{"alias":"fast",...},"request_id":"..."}`. The cost depends on the prices in `terraform.tfvars`. Repeat with `"model":"balanced"` and `"model":"best"` |
| **Common errors** | Every error the API returns is listed in [API_REFERENCE.md](API_REFERENCE.md#errors). In Windows PowerShell 5.1, `curl` is an alias for `Invoke-WebRequest`: use the PowerShell commands, or `curl.exe` |

### 13. The guardrails refuse what they should

| Request (Bash, in step 11's shell) | Expected |
|---|---|
| No token: `curl -s -w ' [%{http_code}]' -H "x-api-key: $KEY" "$API/v1/models"` | `UNAUTHORIZED` `[401]` |
| No API key: `curl -s -w ' [%{http_code}]' -H "Authorization: Bearer $TOKEN" "$API/v1/models"` | `INVALID_API_KEY` `[403]` |
| Unapproved model: `curl -s -w ' [%{http_code}]' -H "Authorization: Bearer $TOKEN" -H "x-api-key: $KEY" -d '{"model":"gpt","messages":[{"role":"user","content":"hi"}]}' "$API/v1/chat"` | `invalid_request` `[400]`, listing the allowed aliases |
| Unknown route: `curl -s -w ' [%{http_code}]' -H "x-api-key: $KEY" "$API/v1/nope"` | `not_found` `[404]` |

🏛️ **Well-Architected:** testing the refusals, not just the happy path, is evidence for the review that authentication, the model allowlist and input validation actually work (**Security**).

### 14. The function logs metadata only

| | |
|---|---|
| **Command (Bash / Git Bash)** | `MSYS_NO_PATHCONV=1 aws logs filter-log-events --region <region> --log-group-name /aws/lambda/powerlab-genai-api-chat --filter-pattern '{ $.request_id = * }' --query 'events[].message' --output text` |
| **Command (PowerShell)** | The same line without `MSYS_NO_PATHCONV=1` |
| **Purpose** | Shows the one JSON line the function writes per request |
| **Expected** | Lines with `request_id`, `route`, `client_id`, `model`, `input_tokens`, `output_tokens`, `cost_estimate_usd`, `model_latency_ms`, `status` and `latency_ms`, and **no** prompt or response text (D8) |
| **Common errors** | `... on resource: ...log-group:C:/Program Files/Git/aws/lambda/...`: Git Bash converted the log group name into a Windows path. Keep `MSYS_NO_PATHCONV=1` |

---

## Change

### Remap a model alias

| | |
|---|---|
| **When** | A model is retired, a newer one is approved, or a model is "not available for this account" ([preflight 6.3](PREFLIGHT_CHECKS.md#63-enable-model-access)) |
| **How** | Test the candidate with [preflight check 6.2](PREFLIGHT_CHECKS.md#62-one-real-model-call), change its `source_inference_profile_id` and `price_per_mtok` in `terraform.tfvars`, then steps 6, 7 and 12 |
| **Expected plan** | The changed alias's application inference profile `must be replaced` (its source can't be changed in place, so it gets a new ARN), the Lambda role policy `updated in-place` to allow the new model only, and the function `updated in-place` with the new ARN |
| **Effect on clients** | None: clients send the alias, not the ARN |

🏛️ **Well-Architected:** a model change is a reviewed configuration change, not a code change (**Operational Excellence**), and the role's permissions follow the allowlist automatically (**Security**: least privilege).

### Add an API client

Add a name to `api_clients` in `terraform.tfvars` (for example `["demo", "reporting"]`), then steps 6, 7 and 11. Each client gets its own Cognito app client and API key, so one can be throttled, rotated or removed without affecting the others (**Security**, **Reliability**). Removing a name deletes that client's credentials.

### Change the function code

Edit `lambda/src`, then steps 5, 6, 7 and 12. The plan shows only the function `updated in-place`.

---

## Remove

### 15. Destroy the stack

| | |
|---|---|
| **Command** | `terraform -chdir=terraform destroy` |
| **Purpose** | Removes everything Terraform created. Run it between work sessions: the stack rebuilds in minutes and nothing bills while it's gone |
| **Expected** | A plan listing every resource to destroy, a `yes` confirmation, then `Destroy complete!` |
| **Not removed** | The state bucket and everything from `bootstrap/` (IAM, Cognito user pool, budget). These are account foundations shared by deployments. The Cognito domain, resource server and app clients *are* removed, so the pool returns to its bootstrap state |
| **After a rebuild** | The API URL, client secret and API key change; read them again (step 11) |
