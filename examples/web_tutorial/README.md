# Web Tutorial

A tutorial and a terminal in one web page. It walks through [docs/HOW_TO.md](../../docs/HOW_TO.md) step by step: sign in to AWS with either profile, set the six connection settings, look inside an access token, prompt the model, and see what the API refuses. Every step explains what happens and why, runs the real command when its button is pressed, shows the real output, and gives the same command for your own terminal (PowerShell or Bash).

| File | What it is |
|---|---|
| [`server.py`](server.py) | A small local server (Python standard library only) that runs the page's commands, because a web page can't run programs itself |
| [`index.html`](index.html) | The page: explanations, buttons, terminal output, own-terminal commands |

## Start it

| | |
|---|---|
| **Before you run** | The stack is deployed ([DEPLOYMENT.md](../../docs/DEPLOYMENT.md) steps 1-7). Python 3.10 or later; the AWS CLI and Terraform for steps 1-2; Node.js 18 or later for the Node.js examples. Run from the repository root. No AWS credentials need to be loaded first: the page signs in itself |
| **Command** | `python examples/web_tutorial/server.py` |
| **Purpose** | Starts the server on `http://127.0.0.1:8765/` and opens the page in your browser |
| **Expected** | `GenAI API web tutorial running at http://127.0.0.1:8765/`, and the page opens |
| **Stop** | Ctrl+C in the terminal where it runs. Everything it held is forgotten |
| **Options** | `--port 8766` to use another port; `--no-browser` to open the page yourself |

**Common errors**

| Symptom | Cause | Fix |
|---|---|---|
| `Port 8765 is not available` | Another program (or a second copy of the server) uses the port | Stop the other copy, or add `--port 8766` |
| `The terraform folder was not found` | Not started from a clone of this repository | Run it from the repository root |
| `Not found on PATH: ...` | A tool isn't installed or isn't on PATH | Install it, open a new terminal, start the server again |
| The page says the server isn't running | The server was stopped, or restarted (which changes the page's token) | Start it and reload the page |

## How sign-in works

The page never asks the AWS CLI to sign in by itself, because the CLI would then wait for an MFA code in a terminal nobody is watching. Instead, for each profile it:

1. Reuses your terminal's sign-in if one was made recently: after `aws sts get-caller-identity --profile powerlab-deploy` in a terminal, the CLI keeps the temporary credentials in `~/.aws/cli/cache`. The page uses them while more than 15 minutes are left.
2. Otherwise asks for a 6-digit MFA code and runs `aws sts assume-role` with it, using the profile's `role_arn`, `mfa_serial` and `source_profile` from `~/.aws/config`. The new credentials last one hour and stay in the server's memory only.

## Safety

The server runs commands, so it is built to be safe on a developer machine (Well-Architected **Security**):

| Rule | Why |
|---|---|
| Listens on `127.0.0.1` only | No other computer can reach it |
| Runs only the fixed commands in `server.py`; typed values are passed as single arguments, without a shell, after validation | Nothing typed on the page can become a command |
| Every request needs a random token created at start-up and embedded in the page, and a `Host` header naming the server | Other web sites open in the same browser can't drive it |
| AWS credentials, the client secret, the API key and tokens stay in memory; the page sees only their lengths and output is scrubbed of them | Secrets never reach the browser, the screen or a file |
| Nothing is written to disk | Stopping the server forgets everything |

It is a learning tool for one person on their own machine, not something to deploy or share on a network.
