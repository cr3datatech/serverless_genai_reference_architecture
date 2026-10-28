# How To Call the Model

How to use the deployed API from your own terminal (Bash, Git Bash or PowerShell on your own machine; AWS CloudShell is not needed) and how to build it into your own code. Every model call goes through the API, so it carries the same authentication, throttles, token cap, cost estimate and metadata-only logging whoever calls it.

🏛️ **Well-Architected:** applications never hold AWS credentials or call Bedrock directly. They get a scoped client identity with its own throttle and quota (**Security**, **Reliability**), every answer reports its token usage and cost (**Cost Optimization**), and clients retry with backoff instead of hammering a busy model (**Reliability**, REL05-BP03).

| Section | Use it to |
|---|---|
| [1. Get the connection settings](#1-get-the-connection-settings) | Collect the six values a caller needs, once per terminal window |
| [2. Call from the terminal](#2-call-from-the-terminal) | Ask a question with one command: Python, Node.js, curl or PowerShell |
| [3. Build it into your code](#3-build-it-into-your-code) | Call the model from a Python or Node.js function, including inside an AWS Lambda function |
| [4. Conversations, system prompts and options](#4-conversations-system-prompts-and-options) | Send history, instructions, `max_tokens` and `temperature` |
| [5. Errors and retries](#5-errors-and-retries) | Know which errors to retry and which to fix |
| [6. Give each application its own client](#6-give-each-application-its-own-client) | Separate credentials, throttle and quota per application |

**Before anything here:** the stack is deployed ([DEPLOYMENT.md](DEPLOYMENT.md) steps 1-7). Run the commands from the repository root.

## 1. Get the connection settings

A caller needs six values. None of them is an AWS credential: with these six, a caller on any machine can use the API, and nothing else in AWS.

| Variable | Terraform output | What it is | Sensitive |
|---|---|---|---|
| `GENAI_API_URL` | `api_url` | The API base URL | No |
| `GENAI_TOKEN_URL` | `token_url` | The Cognito token endpoint | No |
| `GENAI_SCOPE` | `oauth_scope` | The OAuth scope the token must carry | No |
| `GENAI_CLIENT_ID` | `client_ids` (one per client name) | The client's identity | No |
| `GENAI_CLIENT_SECRET` | `client_secrets` | The client's password | **Yes** |
| `GENAI_API_KEY` | `api_keys` | Selects the client's usage plan (throttle and daily quota) | **Yes** |

The commands below read them from Terraform and set them as environment variables in the current terminal window. Every example in this guide uses these variable names, so nothing has to be pasted.

| | |
|---|---|
| **Before you run** | Deploy credentials loaded in this terminal ([DEPLOYMENT.md step 2](DEPLOYMENT.md#2-load-deploy-credentials-into-the-shell)), because the values are read from the Terraform state in S3. `terraform init` done in this clone ([step 4](DEPLOYMENT.md#4-initialise-terraform)). Bash also needs Python 3.10 or later (to read JSON) |
| **Commands (Bash / Git Bash)** | `export GENAI_API_URL=$(terraform -chdir=terraform output -raw api_url) GENAI_TOKEN_URL=$(terraform -chdir=terraform output -raw token_url) GENAI_SCOPE=$(terraform -chdir=terraform output -raw oauth_scope)` then `export GENAI_CLIENT_ID=$(terraform -chdir=terraform output -json client_ids \| python -c "import sys,json;print(json.load(sys.stdin)['demo'])") GENAI_CLIENT_SECRET=$(terraform -chdir=terraform output -json client_secrets \| python -c "import sys,json;print(json.load(sys.stdin)['demo'])") GENAI_API_KEY=$(terraform -chdir=terraform output -json api_keys \| python -c "import sys,json;print(json.load(sys.stdin)['demo'])")` then `echo ${#GENAI_CLIENT_SECRET} ${#GENAI_API_KEY}` |
| **Commands (PowerShell)** | `$env:GENAI_API_URL = terraform -chdir=terraform output -raw api_url; $env:GENAI_TOKEN_URL = terraform -chdir=terraform output -raw token_url; $env:GENAI_SCOPE = terraform -chdir=terraform output -raw oauth_scope` then `$env:GENAI_CLIENT_ID = (terraform -chdir=terraform output -json client_ids \| ConvertFrom-Json).demo; $env:GENAI_CLIENT_SECRET = (terraform -chdir=terraform output -json client_secrets \| ConvertFrom-Json).demo; $env:GENAI_API_KEY = (terraform -chdir=terraform output -json api_keys \| ConvertFrom-Json).demo` then `"$($env:GENAI_CLIENT_SECRET.Length) $($env:GENAI_API_KEY.Length)"` |
| **Purpose** | Sets the six variables for the `demo` client in this window only. Replace `demo` with another client name to act as that client ([section 6](#6-give-each-application-its-own-client)) |
| **Expected** | Two numbers, about `51 40`: the lengths of the secret and the API key (the values themselves aren't printed) |
| **Lasts** | Until the window is closed. The deploy credentials can expire afterwards: the API calls below don't need them |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| `Error: No outputs found` or `Backend initialization required` | Not run from the repository root, or `terraform init` not done in this clone | `cd` to the repository root; [DEPLOYMENT.md step 4](DEPLOYMENT.md#4-initialise-terraform) |
| `ExpiredToken` or `NoCredentialProviders` | Deploy credentials not loaded in this window, or expired | [DEPLOYMENT.md step 2](DEPLOYMENT.md#2-load-deploy-credentials-into-the-shell) |
| `KeyError: 'demo'` / empty value | No client called `demo` in `api_clients` | Use a name from `terraform -chdir=terraform output -json client_ids` |
| Lengths print `0 0` | One of the lines failed, or ran in a different window | Check the output of each line; run all three in the same window |

**On another machine, or in an application:** the six values can be set any other way: an `.env` file outside the repository, a CI secret, or a secret store. Keep the secret and the API key out of source control and out of logs (**Security**, SEC02-BP03). That machine needs no AWS credentials and no Terraform.

## 2. Call from the terminal

Every command in this section needs the six variables from [section 1](#1-get-the-connection-settings) **in the same terminal window**. Check with `echo ${#GENAI_API_KEY}` (PowerShell: `$env:GENAI_API_KEY.Length`): 0 means run section 1 first.

### 2.1 Python (Bash, Git Bash or PowerShell)

| | |
|---|---|
| **Before you run** | Section 1 in this window. Python 3.10 or later. No AWS credentials needed |
| **Command** | `python examples/genai_client.py --model balanced "Explain AWS Lambda in two sentences."` |
| **Other forms** | `python examples/genai_client.py --list-models` · `python examples/genai_client.py --model fast --max-tokens 100 --system "Answer in one sentence." "What is a permissions boundary?"` |
| **Purpose** | Gets a token, calls `POST /v1/chat`, prints the answer, then a summary line. Retries with backoff on `429` and `5xx` |
| **Expected** | The answer, then `[balanced \| 15 in / 71 out tokens \| ~$0.00111 \| stop: end_turn \| request ...]` |

`--from-terraform` (as in [examples/README.md](../examples/README.md)) reads the settings straight from Terraform instead of the variables, and needs the deploy credentials loaded.

### 2.2 Node.js (Bash, Git Bash or PowerShell)

| | |
|---|---|
| **Before you run** | Section 1 in this window. Node.js 18 or later. No AWS credentials needed |
| **Command** | `node examples/genai_client.mjs "Explain AWS Lambda in two sentences." balanced` |
| **Purpose** | The same as 2.1, with the Node.js client ([examples/genai_client.mjs](../examples/genai_client.mjs)) |
| **Expected** | The answer, then the same summary line |

### 2.3 curl (Bash / Git Bash)

Two commands: get a token, then call. The token lasts 60 minutes; reuse it rather than fetching one per call (every token issued is billed).

| | |
|---|---|
| **Before you run** | Section 1 in this window. `curl` and Python 3.10 or later. No AWS credentials needed |
| **Command (token)** | `TOKEN=$(curl -s -d "grant_type=client_credentials&scope=$GENAI_SCOPE&client_id=$GENAI_CLIENT_ID&client_secret=$GENAI_CLIENT_SECRET" "$GENAI_TOKEN_URL" \| python -c "import sys,json;print(json.load(sys.stdin)['access_token'])"); echo ${#TOKEN}` |
| **Command (call)** | `curl -s -H "Authorization: Bearer $TOKEN" -H "x-api-key: $GENAI_API_KEY" -H "content-type: application/json" -d '{"model":"fast","messages":[{"role":"user","content":"Explain AWS Lambda in two sentences."}]}' "$GENAI_API_URL/v1/chat"` |
| **Purpose** | The raw HTTP calls, as any language would make them |
| **Expected** | A number around 800-900 for the token, then `{"output":"...","stop_reason":"end_turn","usage":{...},"cost_estimate_usd":...,"model":{...},"request_id":"..."}` |
| **Note** | In Git Bash on Windows, keep the JSON in single quotes as shown. A question containing a single quote is easier from Python or Node.js (2.1, 2.2) |

### 2.4 PowerShell without Python or Node.js

| | |
|---|---|
| **Before you run** | Section 1 in this window. Windows PowerShell 5.1 or PowerShell 7. No AWS credentials needed |
| **Command (token)** | `$token = (Invoke-RestMethod -Method Post -Uri $env:GENAI_TOKEN_URL -Body @{grant_type='client_credentials'; scope=$env:GENAI_SCOPE; client_id=$env:GENAI_CLIENT_ID; client_secret=$env:GENAI_CLIENT_SECRET}).access_token; $token.Length` |
| **Command (call)** | `$h = @{Authorization="Bearer $token"; 'x-api-key'=$env:GENAI_API_KEY}; $body = @{model='fast'; messages=@(@{role='user'; content='Explain AWS Lambda in two sentences.'})} \| ConvertTo-Json -Depth 5; (Invoke-RestMethod -Method Post -Uri "$env:GENAI_API_URL/v1/chat" -Headers $h -ContentType 'application/json' -Body $body).output` |
| **Purpose** | The same two calls with built-in cmdlets. Building the body with `ConvertTo-Json` avoids quoting problems |
| **Expected** | A number around 800-900, then the answer text |
| **Note** | In Windows PowerShell 5.1, `curl` is an alias for `Invoke-WebRequest`, so the curl commands in 2.3 don't work there; use these, or `curl.exe` |

### Calling Bedrock directly, without the API

An operator can call a model directly with the AWS CLI and the deploy credentials ([DEPLOYMENT.md step 10](DEPLOYMENT.md#10-a-model-call-through-an-application-profile)). That is a test of the model path only: it bypasses the API's authentication, throttles, token cap, cost estimate and logging, and needs AWS credentials with Bedrock permissions. Applications should always use the API.

## 3. Build it into your code

The two example clients are single files with no dependencies beyond the language's standard library. Copy the one for your language into your project, set the six variables from [section 1](#1-get-the-connection-settings) in the environment the code runs in, and call it. Create the client once and reuse it: the token is cached and renewed a minute before it expires.

### 3.1 Python

```python
from genai_client import GenAIClient, Settings, ApiError   # copy examples/genai_client.py next to your code

client = GenAIClient(Settings.from_env())                  # once, at start-up

def ask(question: str, model: str = "fast") -> str:
    """Returns the model's answer to one question."""
    return client.chat(question, model=model, max_tokens=300)["output"]

try:
    print(ask("Explain AWS Lambda in two sentences."))
except ApiError as e:
    print(f"API error {e.status} {e.type}, request {e.request_id}")
```

`client.chat()` returns the whole response (`output`, `usage`, `cost_estimate_usd`, `stop_reason`, `model`, `request_id`), described in [API_REFERENCE.md](API_REFERENCE.md#response-200). For full control, including conversation history, use `client.request("POST", "/v1/chat", body)` with a body as in [section 4](#4-conversations-system-prompts-and-options).

| | |
|---|---|
| **Before you run** | Section 1 in this window (or the six variables set in the code's environment). Python 3.10 or later |
| **Quick check** | `python -c "import sys; sys.path.insert(0, 'examples'); from genai_client import GenAIClient, Settings; print(GenAIClient(Settings.from_env()).chat('Reply with the single word: hello', model='fast', max_tokens=20)['output'])"` |
| **Expected** | `hello` |

### 3.2 Node.js / TypeScript

```js
import { ask, chat, ApiError } from "./genai_client.mjs";  // copy examples/genai_client.mjs next to your code

try {
  console.log(await ask("Explain AWS Lambda in two sentences.", "balanced"));

  const r = await chat({ model: "fast", max_tokens: 300, messages: [{ role: "user", content: "What is Amazon Bedrock?" }] });
  console.log(r.output, r.usage, r.cost_estimate_usd);
} catch (e) {
  if (e instanceof ApiError) console.error(`API error ${e.status} ${e.type}, request ${e.requestId}`);
  else throw e;
}
```

The file is plain JavaScript (ES module) and works from TypeScript as is; it uses the built-in `fetch`, so it needs Node.js 18 or later.

| | |
|---|---|
| **Before you run** | Section 1 in this window (or the six variables set in the code's environment). Node.js 18 or later |
| **Quick check** | `node --input-type=module -e "import { ask } from './examples/genai_client.mjs'; console.log(await ask('Reply with the single word: hello', 'fast'));"` |
| **Expected** | `hello` |

### 3.3 Other languages

Any language with an HTTP client works. The contract is two requests:

1. `POST $GENAI_TOKEN_URL`, form-encoded `grant_type=client_credentials&scope=...&client_id=...&client_secret=...`. Keep `access_token` until a minute before `expires_in` (3600 seconds) runs out.
2. `POST $GENAI_API_URL/v1/chat` with headers `Authorization: Bearer <access_token>`, `x-api-key: <api key>`, `content-type: application/json`, and a JSON body ([section 4](#4-conversations-system-prompts-and-options)).

Set a client timeout of at least 30 seconds: the API answers within 29 seconds or returns `504`. The full contract is in [API_REFERENCE.md](API_REFERENCE.md).

### 3.4 Inside an AWS Lambda function (or any AWS compute)

A function in another stack calls this API like any other client. The pattern:

| Concern | Do this | Why |
|---|---|---|
| **Credentials** | Its own API client ([section 6](#6-give-each-application-its-own-client)). Put the client secret and API key in AWS Systems Manager Parameter Store as `SecureString` parameters (standard parameters are free) or in AWS Secrets Manager (about $0.40 per secret per month, adds rotation). Pass only the parameter names in environment variables | Secrets never sit in plain environment variables or code (**Security**, SEC02-BP03) |
| **Permissions** | The function's role gets `ssm:GetParameter` on those parameters only (with the default `aws/ssm` key no extra KMS permission is needed). It needs **no** Bedrock permissions | Least privilege; model access stays behind the API (**Security**, SEC03-BP02) |
| **Token reuse** | Create the client outside the handler, so warm invocations reuse the cached token | Fewer token requests, lower latency and cost (**Performance Efficiency**, **Cost Optimization**) |
| **Timeouts and retries** | Function timeout at least 35 seconds; lower the client's retries (`max_attempts=2`) so retries fit inside it | The API can take up to 29 seconds; retries must not outlive the function (**Reliability**) |

```python
import os
import boto3
from genai_client import GenAIClient, Settings   # examples/genai_client.py packaged with the function

ssm = boto3.client("ssm")

def secret(name: str) -> str:
    return ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]

# Runs once per execution environment; warm invocations reuse the client and its token.
client = GenAIClient(Settings(
    api_url=os.environ["GENAI_API_URL"],
    token_url=os.environ["GENAI_TOKEN_URL"],
    scope=os.environ["GENAI_SCOPE"],
    client_id=os.environ["GENAI_CLIENT_ID"],
    client_secret=secret(os.environ["GENAI_CLIENT_SECRET_PARAM"]),
    api_key=secret(os.environ["GENAI_API_KEY_PARAM"]),
), max_attempts=2)

def handler(event, context):
    r = client.chat(event["question"], model=event.get("model", "fast"), max_tokens=300)
    return {"answer": r["output"], "cost_estimate_usd": r["cost_estimate_usd"], "request_id": r["request_id"]}
```

This is a pattern for a separate stack, not part of this deployment. Its requests count against the client's usage plan like any other caller.

## 4. Conversations, system prompts and options

The API keeps no state between calls. To continue a conversation, send the whole history each time, oldest first, with roles alternating `user`, `assistant`, `user`; the first and last messages are `user`.

```json
{
  "model": "fast",
  "system": "Answer in one short sentence.",
  "max_tokens": 100,
  "temperature": 0.2,
  "messages": [
    { "role": "user", "content": "My favourite AWS service is Lambda." },
    { "role": "assistant", "content": "Noted." },
    { "role": "user", "content": "Which service did I say was my favourite?" }
  ]
}
```

| Field | Use | Limits |
|---|---|---|
| `model` | `fast`, `balanced` or `best` (list them with `GET /v1/models`). Default `fast` | Aliases only, never raw model IDs |
| `system` | Instructions that apply to the whole conversation | Non-empty string |
| `messages` | The conversation | 1-50 messages, whole body at most 64 KB |
| `max_tokens` | Upper bound on the answer's length, and so its cost | Values above the server cap (1024) are reduced to it |
| `temperature` | 0 for consistent answers, higher for more varied ones | 0 to 1 |

Each call's input tokens include the whole history, so long conversations cost more per turn (**Cost Optimization**). Keep only what the model needs. When `stop_reason` is `max_tokens`, the answer was cut off: ask for a shorter answer or raise `max_tokens`.

## 5. Errors and retries

Every error has the shape `{"error":{"type":"...","message":"...","request_id":"..."}}`. Both example clients already retry the retryable ones with exponential backoff and jitter, and raise the rest as `ApiError`.

| Status / `type` | Retry? | What to do |
|---|---|---|
| `429 THROTTLED`, `429 rate_limited` | Yes, with backoff | The client, the whole API or the model is busy |
| `502`, `503`, `504`, `500` | Yes, a limited number of times | `504 timeout`: lower `max_tokens` or use a faster alias |
| `429 QUOTA_EXCEEDED` | No | The client's 500 requests for the day are used; resets at UTC midnight |
| `401 UNAUTHORIZED` | Once, with a new token | The token expired or lacks the scope |
| `403 INVALID_API_KEY` | No | Wrong or missing `x-api-key` |
| `400`, `413` | No | Fix the request; the message names the field |

Quote the `request_id` when reporting a problem: it appears in the function's log line and the API access log. Every status is listed in [API_REFERENCE.md](API_REFERENCE.md#errors).

## 6. Give each application its own client

The `demo` client is for trying the API. Give each application, script or team its own client, so each has its own credentials, throttle and daily quota, and can be rotated or removed without affecting the others (**Security**, **Reliability**).

| | |
|---|---|
| **Before you run** | Deploy credentials loaded in this terminal ([DEPLOYMENT.md step 2](DEPLOYMENT.md#2-load-deploy-credentials-into-the-shell)) and `terraform init` done in this clone |
| **Steps** | Add the name to `api_clients` in `terraform/terraform.tfvars` (for example `api_clients = ["demo", "reporting"]`), then plan and apply ([DEPLOYMENT.md steps 6-7](DEPLOYMENT.md#6-plan)), then section 1 with `reporting` in place of `demo` |
| **Purpose** | Creates a Cognito app client and an API key for the new name, in the same usage plan |
| **Expected** | The plan shows 3 to add (app client, API key, usage-plan key) and nothing to change or destroy |
| **Removing** | Removing a name from `api_clients` and applying deletes that client's credentials: its callers get `401` / `403` immediately |
