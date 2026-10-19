"""End-to-end tests against the deployed API.

Exercises the real path - Cognito token, API key and usage plan, the
function, the application inference profiles and the models - and the
refusals: missing token, missing API key, unapproved model, invalid input,
oversized body and unknown route. Testing the controls, not just the happy
path, is the evidence the Well-Architected review needs that they work
(Security: SEC11, Reliability: REL12 test reliability).

Cost: about four short model calls per run, well under 0.01 USD.

Run from the repository root with the deploy credentials loaded
(docs/DEPLOYMENT.md step 2), so the settings can be read from Terraform:

    python tests/test_integration.py

Or set the GENAI_* environment variables described in
examples/genai_client.py and run the same command.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))
from genai_client import ApiError, GenAIClient, Settings  # noqa: E402

HELLO = "Reply with the single word: hello"


def load_settings() -> Settings:
    if os.environ.get("GENAI_API_URL"):
        return Settings.from_env()
    return Settings.from_terraform()


class IntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = load_settings()
        # No retries: a test should see the first answer the API gives.
        cls.client = GenAIClient(cls.settings, max_attempts=1)
        cls.aliases = [m["id"] for m in cls.client.models()]

    def raw(self, method: str, path: str, headers: dict, body: bytes | None = None) -> tuple[int, dict]:
        """A request without the client's defaults, to test the refusals."""
        req = urllib.request.Request(self.settings.api_url + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                return resp.status, json.load(resp)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    # --- happy path ---------------------------------------------------------

    def test_models_lists_aliases_with_one_default(self):
        models = self.client.models()
        self.assertGreaterEqual(len(models), 1)
        self.assertEqual(sum(m["default"] for m in models), 1)
        for m in models:
            self.assertTrue(m["model_id"])

    def test_chat_every_alias(self):
        for alias in self.aliases:
            with self.subTest(alias=alias):
                r, headers = self.client.request("POST", "/v1/chat", {
                    "model": alias, "max_tokens": 20, "messages": [{"role": "user", "content": HELLO}],
                })
                self.assertIn("hello", r["output"].lower())
                self.assertEqual(r["model"]["alias"], alias)
                self.assertGreater(r["usage"]["input_tokens"], 0)
                self.assertGreater(r["usage"]["output_tokens"], 0)
                if r["cost_estimate_usd"] is not None:
                    self.assertGreater(r["cost_estimate_usd"], 0)
                self.assertEqual(headers.get("x-request-id"), r["request_id"])

    def test_max_tokens_above_cap_is_capped_not_rejected(self):
        r = self.client.chat(HELLO, max_tokens=1_000_000)
        self.assertIn("hello", r["output"].lower())

    # --- refusals -----------------------------------------------------------

    def test_no_token_is_401(self):
        status, body = self.raw("GET", "/v1/models", {"x-api-key": self.settings.api_key})
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["type"], "UNAUTHORIZED")

    def test_forged_token_is_401(self):
        status, _ = self.raw("GET", "/v1/models", {
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.e30.x", "x-api-key": self.settings.api_key,
        })
        self.assertEqual(status, 401)

    def test_no_api_key_is_403(self):
        status, body = self.raw("GET", "/v1/models", {"Authorization": f"Bearer {self.client.token()}"})
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["type"], "INVALID_API_KEY")

    def test_unknown_route_is_404(self):
        status, body = self.raw("GET", "/v1/nope", {"x-api-key": self.settings.api_key})
        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["type"], "not_found")

    def test_invalid_requests_are_400_and_cost_nothing(self):
        cases = {
            "unapproved model": {"model": "not-an-alias", "messages": [{"role": "user", "content": "hi"}]},
            "unknown field": {"messages": [{"role": "user", "content": "hi"}], "top_k": 5},
            "empty messages": {"messages": []},
            "starts with assistant": {"messages": [{"role": "assistant", "content": "hi"}]},
            "temperature out of range": {"messages": [{"role": "user", "content": "hi"}], "temperature": 3},
        }
        for name, body in cases.items():
            with self.subTest(name):
                with self.assertRaises(ApiError) as ctx:
                    self.client.request("POST", "/v1/chat", body)
                self.assertEqual(ctx.exception.status, 400)
                self.assertEqual(ctx.exception.type, "invalid_request")

    def test_streaming_not_available_yet(self):
        with self.assertRaises(ApiError) as ctx:
            self.client.request("POST", "/v1/chat", {"stream": True, "messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual((ctx.exception.status, ctx.exception.type), (400, "unsupported"))

    def test_oversized_body_is_413(self):
        big = "x" * 70_000
        with self.assertRaises(ApiError) as ctx:
            self.client.request("POST", "/v1/chat", {"messages": [{"role": "user", "content": big}]})
        self.assertEqual((ctx.exception.status, ctx.exception.type), (413, "request_too_large"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
