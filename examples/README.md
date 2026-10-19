# Examples

Two ways to call the deployed API. Both read their settings from the Terraform outputs, so run them from the repository root with the deploy credentials loaded ([DEPLOYMENT.md step 2](../docs/DEPLOYMENT.md#2-load-deploy-credentials-into-the-shell)).

| File | What it shows |
|---|---|
| [`genai_client.py`](genai_client.py) | A small Python client using only the standard library: cached OAuth token, both auth headers, retries with exponential backoff and jitter on `429` and `5xx`, errors as exceptions. Also used by the [integration tests](../tests/test_integration.py) |
| [`curl_examples.sh`](curl_examples.sh) | The same flow in Bash with curl: token, list models, chat, one refusal |

## Python

| | |
|---|---|
| **List models** | `python examples/genai_client.py --from-terraform --list-models` |
| **Ask a question** | `python examples/genai_client.py --from-terraform --model balanced "Explain AWS Lambda in two sentences."` |
| **Expected** | The answer, then a summary line: `[balanced \| 15 in / 71 out tokens \| ~$0.00111 \| stop: end_turn \| request ...]` |
| **Without Terraform** | Set `GENAI_API_URL`, `GENAI_TOKEN_URL`, `GENAI_SCOPE`, `GENAI_CLIENT_ID`, `GENAI_CLIENT_SECRET` and `GENAI_API_KEY`, then drop `--from-terraform`. This is how a real client application would be configured, with the secret coming from a secret store |
| **Requires** | Python 3.10 or later |

## curl

| | |
|---|---|
| **Command (Bash / Git Bash)** | `bash examples/curl_examples.sh "Your question" balanced` |
| **Expected** | The model list, the chat response JSON, then `UNAUTHORIZED [401]` for the call without a token |

## Errors

| Symptom | Cause | Fix |
|---|---|---|
| `Could not read Terraform outputs` | Deploy credentials not loaded in this shell, or not run from the repository root | [DEPLOYMENT.md step 2](../docs/DEPLOYMENT.md#2-load-deploy-credentials-into-the-shell) |
| `401 UNAUTHORIZED` | Token expired (60 minutes) | The Python client renews automatically; rerun the curl script |
| `429 QUOTA_EXCEEDED` | The client's daily quota (500 requests) is used up | Wait until midnight UTC, or raise `client_throttle.daily_request` |

Every other error is described in [API_REFERENCE.md](../docs/API_REFERENCE.md#errors).
