"""Local web tutorial and terminal for the GenAI API (standard library only).

Serves a page on http://127.0.0.1:<port> that explains, and runs, each step of
docs/HOW_TO.md: checking who you are signed in as, setting the six connection
settings, and calling the model. A browser can't run commands, so this small
server runs them on the page's behalf and returns their output.

Safety rules, because a server that runs commands is a powerful thing:

* Listens on 127.0.0.1 only, so no other machine can reach it.
* Runs only the fixed commands defined below, never free text as a command.
  Values typed on the page (a question, an alias, an MFA code) are passed as
  single arguments, without a shell, after validation.
* Every request must carry a random token generated when the server starts
  and embedded in the page, and a Host header naming this server, so other
  web sites open in the same browser can't drive it.
* AWS credentials and the client secret, API key and access token stay in
  this process's memory. The page only ever sees their lengths, and command
  output is scrubbed of them. Everything is forgotten when the server stops.

Run from the repository root:

    python examples/web_tutorial/server.py

then open the printed address (it opens automatically unless --no-browser).
Stop it with Ctrl+C.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

PROFILES = {"deploy": "powerlab-deploy", "review": "powerlab-review"}
ENV_NAMES = ["GENAI_API_URL", "GENAI_TOKEN_URL", "GENAI_SCOPE", "GENAI_CLIENT_ID", "GENAI_CLIENT_SECRET", "GENAI_API_KEY"]
SECRET_ENV = {"GENAI_CLIENT_SECRET", "GENAI_API_KEY"}
# Terraform output behind each variable: (output name, one value per client?)
TF_SOURCES = {
    "GENAI_API_URL": ("api_url", False),
    "GENAI_TOKEN_URL": ("token_url", False),
    "GENAI_SCOPE": ("oauth_scope", False),
    "GENAI_CLIENT_ID": ("client_ids", True),
    "GENAI_CLIENT_SECRET": ("client_secrets", True),
    "GENAI_API_KEY": ("api_keys", True),
}

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
MFA_RE = re.compile(r"^\d{6}$")
NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW: no console pops up

TOOLS = {"aws": shutil.which("aws"), "terraform": shutil.which("terraform"),
         "node": shutil.which("node"), "python": sys.executable}

# Run by the "get a token" step: fetches a token and prints what's inside it,
# never the token itself.
TOKEN_SNIPPET = r'''
import base64, json, os, time, urllib.parse, urllib.request
form = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": os.environ["GENAI_SCOPE"],
    "client_id": os.environ["GENAI_CLIENT_ID"], "client_secret": os.environ["GENAI_CLIENT_SECRET"]}).encode()
req = urllib.request.Request(os.environ["GENAI_TOKEN_URL"], data=form, method="POST")
with urllib.request.urlopen(req, timeout=15) as resp:
    t = json.load(resp)
payload = t["access_token"].split(".")[1]
claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
print(f"token_type {t['token_type']} | expires_in {t['expires_in']} seconds | length {len(t['access_token'])} characters")
print("Claims inside the token (the token itself is not printed):")
for k in ["iss", "client_id", "scope", "token_use", "iat", "exp"]:
    v = claims.get(k)
    if k in ("iat", "exp"):
        v = f"{v}  ({time.strftime('%H:%M:%S UTC', time.gmtime(v))})"
    print(f"  {k:<10} {v}")
'''.strip()

# Run by the "raw HTTP" examples: one request, printed in full.
RAW_SNIPPET = r'''
import json, os, sys, urllib.error, urllib.parse, urllib.request
spec = json.loads(sys.argv[1])
headers = {"content-type": "application/json"}
if "token" not in spec["omit"]:
    form = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": os.environ["GENAI_SCOPE"],
        "client_id": os.environ["GENAI_CLIENT_ID"], "client_secret": os.environ["GENAI_CLIENT_SECRET"]}).encode()
    with urllib.request.urlopen(urllib.request.Request(os.environ["GENAI_TOKEN_URL"], data=form, method="POST"), timeout=15) as resp:
        headers["Authorization"] = "Bearer " + json.load(resp)["access_token"]
if "api_key" not in spec["omit"]:
    headers["x-api-key"] = os.environ["GENAI_API_KEY"]
data = json.dumps(spec["body"]).encode() if spec.get("body") is not None else None
req = urllib.request.Request(os.environ["GENAI_API_URL"] + spec["path"], data=data, method=spec["method"], headers=headers)
try:
    with urllib.request.urlopen(req, timeout=35) as resp:
        status, text = resp.status, resp.read().decode()
except urllib.error.HTTPError as e:
    status, text = e.code, e.read().decode()
print(f"{spec['method']} {spec['path']}  ->  HTTP {status}")
print("Headers sent: " + ", ".join(headers))
if data:
    print("Body sent:")
    print(json.dumps(spec["body"], indent=2))
print("Response body:")
try:
    print(json.dumps(json.loads(text), indent=2))
except ValueError:
    print(text)
'''.strip()

_CONVERSATION = [
    {"role": "user", "content": "My favourite AWS service is Lambda."},
    {"role": "assistant", "content": "Noted."},
    {"role": "user", "content": "Which service did I say was my favourite, and what does it do?"},
]
RAW_PRESETS = {
    "chat_json": {"method": "POST", "path": "/v1/chat", "omit": [],
                  "body": {"model": "fast", "max_tokens": 120,
                           "messages": [{"role": "user", "content": "Explain Amazon Bedrock in one sentence."}]}},
    "conversation": {"method": "POST", "path": "/v1/chat", "omit": [],
                     "body": {"model": "fast", "system": "Answer in two short sentences.", "max_tokens": 150,
                              "messages": _CONVERSATION}},
    "no_token": {"method": "GET", "path": "/v1/models", "omit": ["token"]},
    "no_api_key": {"method": "GET", "path": "/v1/models", "omit": ["api_key"]},
    "bad_alias": {"method": "POST", "path": "/v1/chat", "omit": [],
                  "body": {"model": "turbo", "messages": [{"role": "user", "content": "Hello"}]}},
    "bad_roles": {"method": "POST", "path": "/v1/chat", "omit": [],
                  "body": {"model": "fast", "messages": [{"role": "assistant", "content": "Hello"}]}},
    "unknown_route": {"method": "GET", "path": "/v1/nothing-here", "omit": []},
}


class Fail(Exception):
    """A problem to explain on the page (not a server error)."""


# --- state ----------------------------------------------------------------------

LOCK = threading.Lock()          # one command at a time, like a terminal
CREDS: dict[str, dict] = {}      # profile key -> temporary AWS credentials
ENV: dict[str, str] = {}         # the six GENAI_* settings


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_time(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def known_secrets() -> list[str]:
    vals = [c.get(k, "") for c in CREDS.values() for k in ("AccessKeyId", "SecretAccessKey", "SessionToken")]
    vals += [ENV[k] for k in SECRET_ENV if k in ENV]
    return [v for v in vals if v and len(v) >= 8]


def scrub(text: str) -> str:
    for v in known_secrets():
        text = text.replace(v, "****")
    # Anything that still looks like a JWT (an access token) is hidden too.
    return re.sub(r"eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}", "<token hidden>", text)


def base_env() -> dict:
    drop = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_CREDENTIAL_EXPIRATION",
            "AWS_PROFILE", "GENAI_")
    env = {k: v for k, v in os.environ.items() if not k.startswith(drop)}
    env["AWS_PAGER"] = ""
    return env


def aws_env(key: str) -> dict:
    c = CREDS.get(key)
    if not c or parse_time(c["Expiration"]) < now() + dt.timedelta(minutes=1):
        CREDS.pop(key, None)
        raise Fail(f"Not signed in as {PROFILES[key]}. Do step 1 for this profile first.")
    env = base_env()
    env.update(AWS_ACCESS_KEY_ID=c["AccessKeyId"], AWS_SECRET_ACCESS_KEY=c["SecretAccessKey"],
               AWS_SESSION_TOKEN=c["SessionToken"])
    if c.get("Region"):
        env["AWS_REGION"] = env["AWS_DEFAULT_REGION"] = c["Region"]
    return env


def api_env() -> dict:
    missing = [n for n in ENV_NAMES if not ENV.get(n)]
    if missing:
        raise Fail("Not set yet: " + ", ".join(missing) + ". Do step 2 first.")
    env = base_env()  # deliberately no AWS credentials: the API doesn't need them
    env.update(ENV)
    return env


def tool(name: str) -> str:
    path = TOOLS.get(name)
    if not path:
        raise Fail(f"'{name}' was not found on PATH. Install it, open a new terminal and start the server again.")
    return path


def run(argv: list[str], env: dict, timeout: int = 60, clean: bool = True) -> dict:
    started = time.time()
    try:
        r = subprocess.run(argv, cwd=REPO, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=NO_WINDOW)
        out, err, code = r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        out, err, code = "", f"Stopped after {timeout} seconds without an answer.", -1
    if clean:
        out, err = scrub(out), scrub(err)
    return {"exit_code": code, "stdout": out, "stderr": err, "ms": int((time.time() - started) * 1000)}


def result(display: str, r: dict, note: str = "") -> dict:
    return {"command": display, **r, "note": note}


def message(display: str, text: str) -> dict:
    return {"command": display, "exit_code": 0, "stdout": text, "stderr": "", "ms": 0, "note": ""}


# --- step 1: who am I signed in as ------------------------------------------------

def profile_config(key: str) -> dict:
    name = PROFILES[key]
    cfg = {}
    for k in ("role_arn", "mfa_serial", "source_profile", "region"):
        r = subprocess.run([tool("aws"), "configure", "get", k, "--profile", name], env=base_env(),
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20,
                           creationflags=NO_WINDOW)
        cfg[k] = r.stdout.strip()
    if not cfg["role_arn"]:
        raise Fail(f"Profile {name} has no role_arn in ~/.aws/config. See bootstrap/iam/README.md.")
    return cfg


def creds_from_cli_cache(cfg: dict) -> dict | None:
    """Reuses the sign-in the AWS CLI cached after an MFA prompt in a terminal."""
    role_name = cfg["role_arn"].rsplit("/", 1)[-1]
    best = None
    for f in glob.glob(os.path.expanduser("~/.aws/cli/cache/*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
            arn = d["AssumedRoleUser"]["Arn"]
            c = d["Credentials"]
        except (OSError, ValueError, KeyError):
            continue
        # The CLI itself refreshes (and asks for MFA again) in the last 15
        # minutes, so only reuse a sign-in with more time left than that.
        if f":assumed-role/{role_name}/" in arn and parse_time(c["Expiration"]) > now() + dt.timedelta(minutes=15):
            if best is None or c["Expiration"] > best["Expiration"]:
                best = {**c, "Arn": arn}
    return best


def identity_check(key: str) -> dict:
    cfg = profile_config(key)
    display = f"aws sts get-caller-identity --profile {PROFILES[key]}"
    if key in CREDS and parse_time(CREDS[key]["Expiration"]) > now() + dt.timedelta(minutes=1):
        note = "Using the sign-in this page made earlier."
    else:
        cached = creds_from_cli_cache(cfg)
        if not cached:
            return {"command": display, "exit_code": None, "stdout": "", "stderr": "", "ms": 0, "needs_mfa": True,
                    "note": "No sign-in with more than 15 minutes left was found. "
                            "Enter the 6-digit code from your MFA device and choose Sign in with MFA."}
        CREDS[key] = {**cached, "Region": cfg["region"], "Source": "your terminal's sign-in (AWS CLI cache)"}
        note = "Reusing the sign-in your terminal made earlier (found in the AWS CLI cache)."
    r = run([tool("aws"), "sts", "get-caller-identity", "--output", "json"], aws_env(key), timeout=30)
    if r["exit_code"] != 0:
        CREDS.pop(key, None)
    return result(display, r, note)


def identity_mfa(key: str, code: str) -> dict:
    if not MFA_RE.match(code or ""):
        raise Fail("The MFA code is the 6 digits shown on your authenticator app.")
    cfg = profile_config(key)
    if not cfg["mfa_serial"] or not cfg["source_profile"]:
        raise Fail(f"Profile {PROFILES[key]} needs mfa_serial and source_profile in ~/.aws/config.")
    session = f"web-tutorial-{int(time.time())}"
    argv = [tool("aws"), "sts", "assume-role", "--role-arn", cfg["role_arn"], "--role-session-name", session,
            "--serial-number", cfg["mfa_serial"], "--token-code", code, "--duration-seconds", "3600",
            "--profile", cfg["source_profile"], "--output", "json"]
    display = (f"aws sts assume-role --role-arn {cfg['role_arn']} --role-session-name {session} "
               f"--serial-number {cfg['mfa_serial']} --token-code ****** --duration-seconds 3600 "
               f"--profile {cfg['source_profile']}")
    # Not scrubbed yet because the new credentials aren't known; the output
    # is replaced below before anything reaches the page.
    r = run(argv, base_env(), timeout=30, clean=False)
    if r["exit_code"] != 0:
        r["stdout"], r["stderr"] = scrub(r["stdout"]), scrub(r["stderr"])
        return result(display, r, "Sign-in failed: nothing was stored.")
    d = json.loads(r["stdout"])
    CREDS[key] = {**d["Credentials"], "Arn": d["AssumedRoleUser"]["Arn"], "Region": cfg["region"],
                  "Source": "MFA sign-in from this page"}
    shown = {"AssumedRoleUser": d["AssumedRoleUser"],
             "Credentials": {"AccessKeyId": "****", "SecretAccessKey": "****", "SessionToken": "****",
                             "Expiration": d["Credentials"]["Expiration"]}}
    check = run([tool("aws"), "sts", "get-caller-identity", "--output", "json"], aws_env(key), timeout=30)
    r["stdout"] = (json.dumps(shown, indent=4) + "\n\n$ aws sts get-caller-identity   (with the new credentials)\n"
                   + check["stdout"] + check["stderr"])
    return result(display, r, "Signed in. The temporary credentials are held in this server's memory only, for one hour.")


def identity_forget(key: str) -> dict:
    CREDS.pop(key, None)
    return message(f"(forget the {PROFILES[key]} credentials held by this page)",
                   "Forgotten. Your terminal's own sign-in, if any, is not affected.")


# --- step 2: the six connection settings --------------------------------------------

def tf_output(name: str, client: str) -> tuple[str, dict]:
    output, per_client = TF_SOURCES[name]
    flag = "-json" if per_client else "-raw"
    display = f"terraform -chdir=terraform output {flag} {output}"
    r = run([tool("terraform"), "-chdir=terraform", "output", flag, output], aws_env("deploy"), timeout=90, clean=False)
    value = ""
    if r["exit_code"] == 0:
        if per_client:
            display += f"      (then pick the '{client}' entry)"
            try:
                value = json.loads(r["stdout"])[client]
            except (ValueError, KeyError):
                r["exit_code"], r["stderr"] = 1, f"No client called '{client}' in the {output} output."
        else:
            value = r["stdout"].strip()
    if value:
        ENV[name] = value
        r["stdout"] = f"{name} = " + (f"<hidden: {len(value)} characters>" if name in SECRET_ENV else value)
    else:
        r["stdout"] = ""
    r["stderr"] = scrub(r["stderr"])
    return display, r


def env_terraform(names: list[str], client: str) -> dict:
    if not NAME_RE.match(client or ""):
        raise Fail("A client name is lower-case letters, digits, '-' or '_'.")
    if not names or any(n not in TF_SOURCES for n in names):
        raise Fail("Unknown variable.")
    aws_env("deploy")  # fail early, with a clear message, if not signed in
    lines, outs, errs, code, ms = [], [], [], 0, 0
    for n in names:
        display, r = tf_output(n, client)
        lines.append(display)
        if r["stdout"]:
            outs.append(r["stdout"])
        if r["stderr"].strip():
            errs.append(r["stderr"].strip())
        ms += r["ms"]
        if r["exit_code"] != 0:
            code = r["exit_code"]
            break
    return {"command": "\n".join(lines), "exit_code": code, "stdout": "\n".join(outs),
            "stderr": "\n".join(errs), "ms": ms, "note": ""}


def env_manual(values: dict) -> dict:
    clean = {}
    for n in ENV_NAMES:
        v = str(values.get(n) or "").strip()
        if not v or len(v) > 2048 or "\n" in v or "\r" in v:
            raise Fail(f"{n} is empty or not a single line.")
        clean[n] = v
    ENV.update(clean)
    out = "\n".join(f"{n} = " + (f"<hidden: {len(ENV[n])} characters>" if n in SECRET_ENV else ENV[n])
                    for n in ENV_NAMES)
    return message("(set the six variables by hand)", out)


def env_clear() -> dict:
    ENV.clear()
    return message("(clear the six variables held by this page)", "Cleared.")


# --- steps 3 and 4: token and model calls --------------------------------------------

def show_snippet(code: str, arg: str | None = None) -> str:
    head = "python - " + ("'" + arg + "' " if arg else "") + "<<'EOF'"
    return head + "\n" + code + "\nEOF"


def quote(a: str) -> str:
    if a and not re.search(r"[\s\"'$`]", a):
        return a
    return '"' + a.replace('"', '\\"') + '"'


def api_token() -> dict:
    return result(show_snippet(TOKEN_SNIPPET), run([tool("python"), "-c", TOKEN_SNIPPET], api_env(), timeout=30))


def api_models(client: str) -> dict:
    if client == "node":
        code = ("import('./examples/genai_client.mjs')"
                ".then(async m => console.log(JSON.stringify(await m.models(), null, 2)))")
        return result(f'node -e "{code}"', run([tool("node"), "-e", code], api_env()))
    return result("python examples/genai_client.py --list-models",
                  run([tool("python"), "examples/genai_client.py", "--list-models"], api_env()))


def api_ask(p: dict) -> dict:
    prompt = str(p.get("prompt") or "").strip()
    alias = str(p.get("model") or "").strip()
    system = str(p.get("system") or "").strip()
    max_tokens = p.get("max_tokens")
    client = p.get("client") or "python"
    if not prompt or len(prompt) > 4000:
        raise Fail("Type a question (up to 4000 characters).")
    if alias and not NAME_RE.match(alias):
        raise Fail("An alias is lower-case letters, digits, '-' or '_' (for example fast).")
    if len(system) > 2000:
        raise Fail("Keep the system prompt under 2000 characters.")
    if max_tokens in (None, ""):
        max_tokens = None
    else:
        try:
            max_tokens = int(max_tokens)
        except (TypeError, ValueError):
            raise Fail("max_tokens is a whole number.")
        if not 1 <= max_tokens <= 4096:
            raise Fail("max_tokens is between 1 and 4096 (the API reduces it to its own cap).")
    note = ""
    if client == "node":
        args = [prompt] + ([alias] if alias else [])
        argv = [tool("node"), "examples/genai_client.mjs", *args]
        display = "node examples/genai_client.mjs " + " ".join(quote(a) for a in args)
        if system or max_tokens:
            note = "The Node.js command line takes the question and alias only; the system prompt and max_tokens were not sent."
    else:
        args = []
        if alias:
            args += ["--model", alias]
        if max_tokens:
            args += ["--max-tokens", str(max_tokens)]
        if system:
            args += ["--system", system]
        args.append(prompt)
        argv = [tool("python"), "examples/genai_client.py", *args]
        display = "python examples/genai_client.py " + " ".join(quote(a) for a in args)
    return result(display, run(argv, api_env()), note)


def api_raw(preset: str) -> dict:
    spec = RAW_PRESETS.get(preset)
    if not spec:
        raise Fail("Unknown example.")
    arg = json.dumps(spec)
    return result(show_snippet(RAW_SNIPPET, arg), run([tool("python"), "-c", RAW_SNIPPET, arg], api_env()))


# --- HTTP -----------------------------------------------------------------------------

def state() -> dict:
    profiles = {}
    for key, name in PROFILES.items():
        c = CREDS.get(key)
        if c and parse_time(c["Expiration"]) < now():
            CREDS.pop(key, None)
            c = None
        profiles[key] = {"profile": name, "signed_in": bool(c), "arn": c["Arn"] if c else None,
                         "expires": c["Expiration"] if c else None, "source": c.get("Source") if c else None}
    env = {}
    for n in ENV_NAMES:
        shown = None
        if n in ENV:
            shown = f"<hidden: {len(ENV[n])} characters>" if n in SECRET_ENV else ENV[n]
        env[n] = {"set": n in ENV, "secret": n in SECRET_ENV, "shown": shown}
    return {"profiles": profiles, "env": env, "tools": {k: bool(v) for k, v in TOOLS.items()}}


def _profile(p: dict) -> str:
    key = p.get("profile")
    if key not in PROFILES:
        raise Fail("Unknown profile.")
    return key


ACTIONS = {
    "identity.check": lambda p: identity_check(_profile(p)),
    "identity.mfa": lambda p: identity_mfa(_profile(p), str(p.get("code", "")).strip()),
    "identity.forget": lambda p: identity_forget(_profile(p)),
    "env.terraform": lambda p: env_terraform(p.get("names") or ENV_NAMES, p.get("client") or "demo"),
    "env.manual": lambda p: env_manual(p.get("values") or {}),
    "env.clear": lambda p: env_clear(),
    "api.token": lambda p: api_token(),
    "api.models": lambda p: api_models(p.get("client") or "python"),
    "api.ask": api_ask,
    "api.raw": lambda p: api_raw(p.get("preset", "")),
}


class Handler(BaseHTTPRequestHandler):
    server_version = "GenAITutorial"
    token = ""
    nonce = ""
    hosts: set = set()

    def log_message(self, fmt, *args):  # keep the terminal quiet; the page shows everything
        pass

    def _send(self, status: int, body: bytes, ctype: str):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         f"default-src 'none'; script-src 'nonce-{self.nonce}'; style-src 'unsafe-inline'; "
                         "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; "
                         "frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj: dict):
        self._send(status, json.dumps(obj).encode(), "application/json")

    def _host_ok(self) -> bool:
        return self.headers.get("Host", "") in self.hosts

    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"error": "Unexpected Host header."})
        if self.path in ("/", "/index.html"):
            html = (HERE / "index.html").read_text(encoding="utf-8")
            html = html.replace("__TUTORIAL_TOKEN__", self.token).replace("__NONCE__", self.nonce)
            return self._send(200, html.encode(), "text/html; charset=utf-8")
        if self.path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        return self._json(404, {"error": "Not found."})

    def do_POST(self):
        if not self._host_ok():
            return self._json(403, {"error": "Unexpected Host header."})
        if not hmac.compare_digest(self.headers.get("X-Tutorial-Token", ""), self.token):
            return self._json(403, {"error": "Missing or wrong page token. Reload the page."})
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._json(415, {"error": "JSON only."})
        length = int(self.headers.get("Content-Length") or 0)
        if length > 65536:
            return self._json(413, {"error": "Request too large."})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json(400, {"error": "Invalid JSON."})
        if self.path == "/api/state":
            return self._json(200, state())
        if self.path != "/api/run":
            return self._json(404, {"error": "Not found."})
        action = ACTIONS.get(body.get("action"))
        if not action:
            return self._json(400, {"error": "Unknown action."})
        if not LOCK.acquire(timeout=1):
            return self._json(409, {"error": "Another command is still running. Wait for it to finish."})
        try:
            out = action(body.get("params") or {})
        except Fail as e:
            out = {"command": "", "exit_code": None, "stdout": "", "stderr": "", "ms": 0, "note": str(e),
                   "refused": True}
        except Exception as e:  # report it on the page, never crash the server
            out = {"command": "", "exit_code": None, "stdout": "", "stderr": scrub(f"{type(e).__name__}: {e}"),
                   "ms": 0, "note": "Unexpected error in the tutorial server."}
        finally:
            LOCK.release()
        out["state"] = state()
        return self._json(200, out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Local web tutorial and terminal for the GenAI API.")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="Don't open the page automatically")
    args = ap.parse_args()
    if not (REPO / "terraform").is_dir():
        print("The terraform folder was not found: run this from a clone of the repository.", file=sys.stderr)
        return 1
    Handler.token = secrets.token_urlsafe(32)
    Handler.nonce = secrets.token_urlsafe(16)
    Handler.hosts = {f"127.0.0.1:{args.port}", f"localhost:{args.port}"}
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as e:
        print(f"Port {args.port} is not available ({e}). Try --port 8766.", file=sys.stderr)
        return 1
    url = f"http://127.0.0.1:{args.port}/"
    print(f"GenAI API web tutorial running at {url}")
    print("It listens on this machine only. Press Ctrl+C to stop; everything it holds is then forgotten.")
    missing = [k for k, v in TOOLS.items() if not v]
    if missing:
        print("Not found on PATH (the steps that need them will say so): " + ", ".join(missing))
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
