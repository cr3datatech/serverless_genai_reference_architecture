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

**Prefer a guided version?** [examples/web_tutorial](../examples/web_tutorial/README.md) is a local web page that walks through sections 1-5, runs each command for you and explains its output. Start it with `python examples/web_tutorial/server.py`.

**Before anything here:** the stack is deployed ([DEPLOYMENT.md](DEPLOYMENT.md) steps 1-7). Run the commands from the repository root.

## 1. Get the connection settings

### 1.1 How a call works

Calling the model is always two HTTP requests:

1. **Get a token.** The caller sends its client ID and client secret (like a username and password for a program) to the **token URL**, asking for the **scope** "may call this API". **Amazon Cognito**, the AWS service that manages identities for this API, checks them and returns an **access token**: a signed string that proves who the caller is. It is valid for 60 minutes and is reused for every call in that time.
2. **Call the API.** The caller sends its question to the **API URL**, with the access token and its **API key** in two headers. **Amazon API Gateway**, the AWS service that receives every request, checks the token, checks the API key, applies the caller's rate limit, and only then passes the request on to the code that calls the model.

The six values below are everything those two requests need. None of them is an AWS credential: a caller with these six can use this API from any machine, and can't do anything else in AWS.

### 1.2 The six environment variables

An **environment variable** is a named value that a terminal window (or a running program) keeps in memory, so commands and code can read it without the value being typed or written into the code. Every example in this guide reads these six names, so nothing has to be pasted into commands.

| Variable | What it is, in plain words | Looks like | Why the caller needs it | Used in | Where it comes from | Secret? |
|---|---|---|---|---|---|---|
| `GENAI_API_URL` | The web address of the API: where questions are sent | `https://<api-id>.execute-api.<region>.amazonaws.com/<stage>` | Without it the caller doesn't know where to send the question. `/v1/chat` and `/v1/models` are added to the end | Request 2 | Terraform output `api_url` | No |
| `GENAI_TOKEN_URL` | The web address of the Cognito "sign-in desk" for programs | `https://<prefix>.auth.<region>.amazoncognito.com/oauth2/token` | The caller must get an access token here before it can call the API | Request 1 | Terraform output `token_url` | No |
| `GENAI_SCOPE` | The name of the permission the token must carry, "may call this API" | `<api-name>/invoke` | API Gateway refuses tokens without this scope (`401`), so a token issued for some other purpose can't be used here | Request 1 | Terraform output `oauth_scope` | No |
| `GENAI_CLIENT_ID` | The caller's username: which registered application is asking | 26 letters and digits | Cognito needs to know which application is signing in. Each application gets its own ([section 6](#6-give-each-application-its-own-client)) | Request 1 | Terraform output `client_ids`, one per client name | No, but don't publish it |
| `GENAI_CLIENT_SECRET` | The caller's password, paired with the client ID | About 50 characters | Proves the caller really is that application. Anyone holding it can get tokens and spend that client's quota | Request 1 | Terraform output `client_secrets` | **Yes** |
| `GENAI_API_KEY` | A key that picks the caller's **usage plan**: its rate limit and daily request quota | 40 letters and digits | API Gateway refuses requests without it (`403`). It isn't proof of identity on its own (that's the token's job); it decides which limits apply | Request 2, header `x-api-key` | Terraform output `api_keys` | **Yes** |

**Keeping the secrets safe:** never put `GENAI_CLIENT_SECRET` or `GENAI_API_KEY` in code, commits, screenshots, tickets or chat. Set them as environment variables, or load them from a secret store such as AWS Systems Manager Parameter Store ([section 3.4](#34-inside-an-aws-lambda-function-or-any-aws-compute)). If one leaks, the operator removes that client and creates a new one (**Security**, SEC02-BP03).

**Terms used above**

| Term | Meaning |
|---|---|
| **Amazon Cognito** | The AWS service that keeps the list of applications allowed to use the API and issues their tokens |
| **OAuth 2.0 client credentials** | The standard way for a program (not a person) to sign in: send ID and secret, get a token back |
| **Access token** | A signed, time-limited string that proves who the caller is. Sent as `Authorization: Bearer <token>` |
| **Scope** | A named permission inside a token; this API accepts only tokens with its own scope |
| **Amazon API Gateway** | The AWS service at the API URL. It checks every request and applies the limits before any model is called, so refused requests cost nothing |
| **Usage plan** | The rate limit (requests per second) and daily quota attached to an API key |
| **Terraform output** | A value the deployment publishes after it creates the resources, read with `terraform output` |

### 1.3 Set the variables

There are two ways to set them, depending on who you are:

| You are | Use | AWS credentials needed? |
|---|---|---|
| The operator who deployed the stack, or someone with the deploy role | **Option A**: read all six from Terraform with one command | Yes, the deploy role, only for this command |
| A developer who was given the six values by the operator | **Option B**: set each one by hand | No |

#### Option A: read them from Terraform

**Before you run:** you're in the repository root, `terraform init` has been done in this clone ([DEPLOYMENT.md step 4](DEPLOYMENT.md#4-initialise-terraform)), and the deploy credentials are loaded in this terminal window, because the values are read from the Terraform state in S3. To load them, run both lines (the first asks for your MFA code):

```
aws sts get-caller-identity --profile powerlab-deploy
```
```
aws configure export-credentials --profile powerlab-deploy --format powershell | Invoke-Expression
```

In Bash / Git Bash, the second line is `eval "$(aws configure export-credentials --profile powerlab-deploy --format env)"`. Details: [DEPLOYMENT.md step 2](DEPLOYMENT.md#2-load-deploy-credentials-into-the-shell).

**Command (PowerShell)**, one line:

```
$env:GENAI_API_URL = terraform -chdir=terraform output -raw api_url; $env:GENAI_TOKEN_URL = terraform -chdir=terraform output -raw token_url; $env:GENAI_SCOPE = terraform -chdir=terraform output -raw oauth_scope; $env:GENAI_CLIENT_ID = (terraform -chdir=terraform output -json client_ids | ConvertFrom-Json).demo; $env:GENAI_CLIENT_SECRET = (terraform -chdir=terraform output -json client_secrets | ConvertFrom-Json).demo; $env:GENAI_API_KEY = (terraform -chdir=terraform output -json api_keys | ConvertFrom-Json).demo; "$($env:GENAI_CLIENT_SECRET.Length) $($env:GENAI_API_KEY.Length)"; $env:GENAI_API_URL
```

**Command (Bash / Git Bash)**, one line (also needs Python 3.10 or later, to read JSON):

```
export GENAI_API_URL=$(terraform -chdir=terraform output -raw api_url) GENAI_TOKEN_URL=$(terraform -chdir=terraform output -raw token_url) GENAI_SCOPE=$(terraform -chdir=terraform output -raw oauth_scope); export GENAI_CLIENT_ID=$(terraform -chdir=terraform output -json client_ids | python -c "import sys,json;print(json.load(sys.stdin)['demo'])") GENAI_CLIENT_SECRET=$(terraform -chdir=terraform output -json client_secrets | python -c "import sys,json;print(json.load(sys.stdin)['demo'])") GENAI_API_KEY=$(terraform -chdir=terraform output -json api_keys | python -c "import sys,json;print(json.load(sys.stdin)['demo'])"); echo ${#GENAI_CLIENT_SECRET} ${#GENAI_API_KEY}; echo $GENAI_API_URL
```

| | |
|---|---|
| **Purpose** | Sets the six variables for the `demo` client in this window only. Replace each `demo` with another client name to act as that client ([section 6](#6-give-each-application-its-own-client)) |
| **Expected** | After a few seconds, two numbers, about `51 40` (the lengths of the secret and the API key; the values themselves aren't printed), then the API URL ending in `.amazonaws.com/<stage>` |
| **Lasts** | Until the window is closed; a new window needs the command again. The deploy credentials can expire afterwards: the API calls below don't need them |

**What each part of the PowerShell command does:**

| Part | Sets | How |
|---|---|---|
| `$env:GENAI_API_URL = terraform -chdir=terraform output -raw api_url` | `GENAI_API_URL` | `terraform output -raw` prints one output as plain text; `-chdir=terraform` runs it in the `terraform` folder; `$env:NAME = ...` stores the result as an environment variable |
| `$env:GENAI_TOKEN_URL = terraform -chdir=terraform output -raw token_url` | `GENAI_TOKEN_URL` | The same, for the token URL |
| `$env:GENAI_SCOPE = terraform -chdir=terraform output -raw oauth_scope` | `GENAI_SCOPE` | The same, for the scope |
| `$env:GENAI_CLIENT_ID = (terraform -chdir=terraform output -json client_ids \| ConvertFrom-Json).demo` | `GENAI_CLIENT_ID` | `client_ids` holds one ID per client, so it is printed as JSON (`-json`), converted to an object (`ConvertFrom-Json`), and the `demo` entry is picked (`.demo`) |
| `$env:GENAI_CLIENT_SECRET = (terraform -chdir=terraform output -json client_secrets \| ConvertFrom-Json).demo` | `GENAI_CLIENT_SECRET` | The same, for the secret. Terraform marks this output sensitive, so `terraform output` on its own hides it; asking for it by name shows it |
| `$env:GENAI_API_KEY = (terraform -chdir=terraform output -json api_keys \| ConvertFrom-Json).demo` | `GENAI_API_KEY` | The same, for the API key (also sensitive) |
| `"$($env:GENAI_CLIENT_SECRET.Length) $($env:GENAI_API_KEY.Length)"; $env:GENAI_API_URL` | (check only) | Prints the lengths of the two secrets, not the secrets, and the API URL, to show everything was set |

The Bash command does the same: `export NAME=$(...)` stores a command's output, and `python -c "..."` picks the `demo` entry out of the JSON.

#### Option B: set them by hand

**Before you run:** the operator has given you the six values through a safe channel (a password manager or secret store, not email or chat). No AWS credentials, Terraform or clone of this repository are needed. Replace each `<...>` with the value you were given, keeping the quotes.

**Command (PowerShell)**, one line:

```
$env:GENAI_API_URL = "<api-url>"; $env:GENAI_TOKEN_URL = "<token-url>"; $env:GENAI_SCOPE = "<scope>"; $env:GENAI_CLIENT_ID = "<client-id>"; $env:GENAI_CLIENT_SECRET = "<client-secret>"; $env:GENAI_API_KEY = "<api-key>"; "$($env:GENAI_CLIENT_SECRET.Length) $($env:GENAI_API_KEY.Length)"
```

**Command (Bash / Git Bash)**, one line:

```
export GENAI_API_URL="<api-url>" GENAI_TOKEN_URL="<token-url>" GENAI_SCOPE="<scope>" GENAI_CLIENT_ID="<client-id>" GENAI_CLIENT_SECRET="<client-secret>" GENAI_API_KEY="<api-key>"; echo ${#GENAI_CLIENT_SECRET} ${#GENAI_API_KEY}
```

| | |
|---|---|
| **Purpose** | Sets the six variables in this window only |
| **Expected** | Two numbers, about `51 40`. Anything much shorter means a value was pasted incompletely |
| **Note** | A command typed with secrets in it is saved in the terminal's history. Clear it afterwards (PowerShell: `Clear-History`, and delete `(Get-PSReadLineOption).HistorySavePath` lines if needed; Bash: `history -c`), or load the values from a secret store instead |

#### Check the variables at any time

| | |
|---|---|
| **Command (PowerShell)** | `Get-ChildItem env:GENAI_* \| Select-Object Name, @{n='Length';e={$_.Value.Length}}` |
| **Command (Bash / Git Bash)** | `for v in GENAI_API_URL GENAI_TOKEN_URL GENAI_SCOPE GENAI_CLIENT_ID GENAI_CLIENT_SECRET GENAI_API_KEY; do val=${!v}; echo "$v ${#val}"; done` |
| **Purpose** | Lists the six names with the length of each value, without showing the values |
| **Expected** | Six names, none with length 0 |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| `Error: No outputs found` or `Backend initialization required` | Not run from the repository root, or `terraform init` not done in this clone | `cd` to the repository root; [DEPLOYMENT.md step 4](DEPLOYMENT.md#4-initialise-terraform) |
| `ExpiredToken` or `NoCredentialProviders` | Deploy credentials not loaded in this window, or expired | [DEPLOYMENT.md step 2](DEPLOYMENT.md#2-load-deploy-credentials-into-the-shell) |
| `No valid credential sources found`, often with `login session has expired, please reauthenticate`, repeated six times, then `0 0` | The deploy credentials loaded in this window have expired (they last about an hour), so Terraform fell back to the machine's default AWS sign-in, which has expired too | Run both commands under **Before you run** again in this window, then the command again |
| `KeyError: 'demo'` / empty value | No client called `demo` in `api_clients` | Use a name from `terraform -chdir=terraform output -json client_ids` |
| Lengths print `0 0` | Part of the command failed, or it ran in a different window | Read the error above the numbers; run the command again in the window you will use |

**On another machine, or in an application:** the six values can be set any other way: an `.env` file outside the repository, a CI secret, or a secret store. Keep the secret and the API key out of source control and out of logs (**Security**, SEC02-BP03). That machine needs no AWS credentials and no Terraform.

## 2. Call from the terminal

Every command in this section needs the six variables from [section 1](#1-get-the-connection-settings) **in the same terminal window**. Check with `echo ${#GENAI_API_KEY}` (PowerShell: `$env:GENAI_API_KEY.Length`): 0 means run section 1 first. Copy one code block at a time: each is one complete command.

### 2.1 Python (Bash, Git Bash or PowerShell)

**Before you run:** section 1 in this window. Python 3.10 or later. No AWS credentials needed.

Each command below is complete on its own: copy one block, run it, then the next.

**List the models you can use:**

```
python examples/genai_client.py --list-models
```

Expected: three aliases (`balanced`, `best`, `fast`), each with the model behind it, and `fast` marked `(default)`.

**Ask a question:**

```
python examples/genai_client.py --model balanced "Explain AWS Lambda in two sentences."
```

Expected: the answer, then a summary line such as `[balanced | 15 in / 71 out tokens | ~$0.00111 | stop: end_turn | request ...]`.

**Ask with instructions and a length limit:**

```
python examples/genai_client.py --model fast --max-tokens 100 --system "Answer in one sentence." "What is a permissions boundary?"
```

Expected: a one-sentence answer, then the summary line.

| | |
|---|---|
| **Purpose** | Gets a token, calls `POST /v1/chat`, prints the answer, then a summary line. Retries with backoff on `429` and `5xx` |
| **Options** | `--model` an alias (default `fast`); `--system` instructions for the whole answer; `--max-tokens` the longest answer allowed; `--list-models` list the aliases instead of asking; the question goes last, in quotes |
| **The summary line** | `in` / `out`: tokens billed. `~$`: the cost estimate the API returns. `stop: end_turn`: the answer is complete (`max_tokens` means it was cut off). `request`: the ID to quote when reporting a problem |
| **Common errors** | `Missing environment variables`: section 1 wasn't run in this window. `python` not found: try `py` (Windows) or `python3`. `unrecognized arguments`: two commands were pasted on one line, or the question isn't in quotes |

`--from-terraform` (as in [examples/README.md](../examples/README.md)) reads the settings straight from Terraform instead of the variables, and needs the deploy credentials loaded.

### 2.2 Node.js (Bash, Git Bash or PowerShell)

**Before you run:** section 1 in this window. Node.js 18 or later. No AWS credentials needed.

```
node examples/genai_client.mjs "Explain AWS Lambda in two sentences." balanced
```

| | |
|---|---|
| **Purpose** | The same as 2.1, with the Node.js client ([examples/genai_client.mjs](../examples/genai_client.mjs)). The question comes first, then the alias (optional, default `fast`) |
| **Expected** | The answer, then the same summary line |

### 2.3 curl (Bash / Git Bash)

Two commands: get a token, then call. The token lasts 60 minutes; reuse it rather than fetching one per call (every token issued is billed).

**Before you run:** section 1 in this window. `curl` and Python 3.10 or later. No AWS credentials needed.

**Get a token** (stored in `TOKEN`; only its length is printed):

```
TOKEN=$(curl -s -d "grant_type=client_credentials&scope=$GENAI_SCOPE&client_id=$GENAI_CLIENT_ID&client_secret=$GENAI_CLIENT_SECRET" "$GENAI_TOKEN_URL" | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])"); echo ${#TOKEN}
```

**Call the API:**

```
curl -s -H "Authorization: Bearer $TOKEN" -H "x-api-key: $GENAI_API_KEY" -H "content-type: application/json" -d '{"model":"fast","messages":[{"role":"user","content":"Explain AWS Lambda in two sentences."}]}' "$GENAI_API_URL/v1/chat"
```

| | |
|---|---|
| **Purpose** | The raw HTTP calls, as any language would make them |
| **Expected** | A number around 800-900 for the token, then `{"output":"...","stop_reason":"end_turn","usage":{...},"cost_estimate_usd":...,"model":{...},"request_id":"..."}` |
| **Note** | In Git Bash on Windows, keep the JSON in single quotes as shown. A question containing a single quote is easier from Python or Node.js (2.1, 2.2). After 60 minutes the call returns `401`: get a new token |

### 2.4 PowerShell without Python or Node.js

**Before you run:** section 1 in this window. Windows PowerShell 5.1 or PowerShell 7. No AWS credentials needed.

**Get a token** (stored in `$token`; only its length is printed):

```
$token = (Invoke-RestMethod -Method Post -Uri $env:GENAI_TOKEN_URL -Body @{grant_type='client_credentials'; scope=$env:GENAI_SCOPE; client_id=$env:GENAI_CLIENT_ID; client_secret=$env:GENAI_CLIENT_SECRET}).access_token; $token.Length
```

**Call the API:**

```
$h = @{Authorization="Bearer $token"; 'x-api-key'=$env:GENAI_API_KEY}; $body = @{model='fast'; messages=@(@{role='user'; content='Explain AWS Lambda in two sentences.'})} | ConvertTo-Json -Depth 5; (Invoke-RestMethod -Method Post -Uri "$env:GENAI_API_URL/v1/chat" -Headers $h -ContentType 'application/json' -Body $body).output
```

| | |
|---|---|
| **Purpose** | The same two calls with built-in cmdlets. Building the body with `ConvertTo-Json` avoids quoting problems |
| **Expected** | A number around 800-900, then the answer text |
| **Note** | In Windows PowerShell 5.1, `curl` is an alias for `Invoke-WebRequest`, so the curl commands in 2.3 don't work there; use these, or `curl.exe`. After 60 minutes the call returns `401`: get a new token |

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

**Quick check** (run from the repository root):

```
python -c "import sys; sys.path.insert(0, 'examples'); from genai_client import GenAIClient, Settings; print(GenAIClient(Settings.from_env()).chat('Reply with the single word: hello', model='fast', max_tokens=20)['output'])"
```

Expected: `hello`.

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

**Quick check** (run from the repository root):

```
node --input-type=module -e "import { ask } from './examples/genai_client.mjs'; console.log(await ask('Reply with the single word: hello', 'fast'));"
```

Expected: `hello`.

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
