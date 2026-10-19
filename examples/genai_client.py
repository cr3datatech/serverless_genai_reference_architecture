"""Minimal Python client for the GenAI API (standard library only).

Shows the client side of the patterns the API expects:

* OAuth 2.0 client-credentials token, cached and reused until shortly
  before it expires (every token issued is billed, and fetching one per
  call adds latency).
* Both headers on every call: `Authorization: Bearer <token>` (who is
  calling) and `x-api-key` (which usage plan applies).
* Retries with exponential backoff and jitter on 429 and 5xx, so clients
  back off together instead of hammering a busy model (Well-Architected
  Reliability: REL05-BP03 control and limit retry calls).

Configuration comes from environment variables, or from the Terraform
outputs with --from-terraform (needs the deploy credentials loaded, see
docs/DEPLOYMENT.md step 2):

    GENAI_API_URL        api_url output
    GENAI_TOKEN_URL      token_url output
    GENAI_SCOPE          oauth_scope output
    GENAI_CLIENT_ID      client ID of one API client
    GENAI_CLIENT_SECRET  that client's secret
    GENAI_API_KEY        that client's API key

Usage:

    python examples/genai_client.py --from-terraform --list-models
    python examples/genai_client.py --from-terraform --model balanced "Explain AWS Lambda in two sentences."
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ApiError(Exception):
    """An error response from the API, in its documented JSON shape."""

    def __init__(self, status: int, error: dict):
        self.status = status
        self.type = error.get("type", "unknown")
        self.request_id = error.get("request_id")
        super().__init__(f"{status} {self.type}: {error.get('message', '')} (request_id {self.request_id})")


@dataclass
class Settings:
    api_url: str
    token_url: str
    scope: str
    client_id: str
    client_secret: str
    api_key: str

    @classmethod
    def from_env(cls) -> "Settings":
        names = ["API_URL", "TOKEN_URL", "SCOPE", "CLIENT_ID", "CLIENT_SECRET", "API_KEY"]
        missing = [f"GENAI_{n}" for n in names if not os.environ.get(f"GENAI_{n}")]
        if missing:
            raise SystemExit(f"Missing environment variables: {', '.join(missing)} (or use --from-terraform)")
        return cls(*(os.environ[f"GENAI_{n}"] for n in names))

    @classmethod
    def from_terraform(cls, client: str = "demo", chdir: str = "terraform") -> "Settings":
        try:
            raw = subprocess.run(
                ["terraform", f"-chdir={chdir}", "output", "-json"],
                check=True, capture_output=True, text=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as e:
            raise SystemExit(f"Could not read Terraform outputs ({e}). Are the deploy credentials loaded?")
        out = {k: v["value"] for k, v in json.loads(raw).items()}
        return cls(
            api_url=out["api_url"],
            token_url=out["token_url"],
            scope=out["oauth_scope"],
            client_id=out["client_ids"][client],
            client_secret=out["client_secrets"][client],
            api_key=out["api_keys"][client],
        )


class GenAIClient:
    def __init__(self, settings: Settings, max_attempts: int = 4, timeout: float = 35.0):
        self.s = settings
        self.max_attempts = max_attempts
        self.timeout = timeout
        self._token: str | None = None
        self._token_expires = 0.0

    # --- authentication -----------------------------------------------------

    def token(self) -> str:
        # Renew a minute early so a token never expires mid-request.
        if self._token is None or time.time() > self._token_expires - 60:
            body = urllib.parse.urlencode({
                "grant_type": "client_credentials",
                "scope": self.s.scope,
                "client_id": self.s.client_id,
                "client_secret": self.s.client_secret,
            }).encode()
            req = urllib.request.Request(self.s.token_url, data=body, method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.load(resp)
            self._token = data["access_token"]
            self._token_expires = time.time() + int(data.get("expires_in", 3600))
        return self._token

    # --- API calls ----------------------------------------------------------

    def request(self, method: str, path: str, body: dict | None = None,
                headers: dict | None = None) -> tuple[dict, dict]:
        """Calls the API; returns (json body, response headers). Raises ApiError."""
        default_headers = {
            "Authorization": f"Bearer {self.token()}",
            "x-api-key": self.s.api_key,
            "content-type": "application/json",
        }
        if headers is not None:
            default_headers.update(headers)
        final_headers = {k: v for k, v in default_headers.items() if v is not None}
        data = json.dumps(body).encode() if body is not None else None

        for attempt in range(1, self.max_attempts + 1):
            req = urllib.request.Request(self.s.api_url + path, data=data, method=method, headers=final_headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.load(resp), dict(resp.headers)
            except urllib.error.HTTPError as e:
                payload = e.read()
                try:
                    error = json.loads(payload).get("error", {})
                except ValueError:
                    error = {"type": "unknown", "message": payload.decode(errors="replace")}
                if e.code in RETRYABLE_STATUS and attempt < self.max_attempts:
                    # Exponential backoff with full jitter: 0-1 s, 0-2 s, 0-4 s ...
                    time.sleep(random.uniform(0, 2 ** (attempt - 1)))
                    continue
                raise ApiError(e.code, error) from None
        raise AssertionError("unreachable")

    def models(self) -> list[dict]:
        return self.request("GET", "/v1/models")[0]["data"]

    def chat(self, prompt: str, model: str | None = None, system: str | None = None,
             max_tokens: int | None = None, temperature: float | None = None) -> dict:
        body: dict = {"messages": [{"role": "user", "content": prompt}]}
        for key, value in [("model", model), ("system", system),
                           ("max_tokens", max_tokens), ("temperature", temperature)]:
            if value is not None:
                body[key] = value
        return self.request("POST", "/v1/chat", body)[0]


def main() -> int:
    p = argparse.ArgumentParser(description="Call the GenAI API.")
    p.add_argument("prompt", nargs="?", help="Question to send")
    p.add_argument("--model", help="Alias: fast, balanced or best (default: the API's default)")
    p.add_argument("--system", help="Optional system prompt")
    p.add_argument("--max-tokens", type=int)
    p.add_argument("--list-models", action="store_true")
    p.add_argument("--from-terraform", action="store_true", help="Read settings from the Terraform outputs")
    p.add_argument("--client", default="demo", help="API client name in Terraform (default: demo)")
    args = p.parse_args()

    settings = Settings.from_terraform(args.client) if args.from_terraform else Settings.from_env()
    client = GenAIClient(settings)
    try:
        if args.list_models:
            for m in client.models():
                print(f"{m['id']:<10} {m['model_id']}{'  (default)' if m['default'] else ''}")
            return 0
        if not args.prompt:
            p.error("a prompt is required unless --list-models is given")
        r = client.chat(args.prompt, model=args.model, system=args.system, max_tokens=args.max_tokens)
    except ApiError as e:
        print(e, file=sys.stderr)
        return 1

    print(r["output"])
    u = r["usage"]
    print(f"\n[{r['model']['alias']} | {u['input_tokens']} in / {u['output_tokens']} out tokens | "
          f"~${r['cost_estimate_usd']} | stop: {r['stop_reason']} | request {r['request_id']}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
