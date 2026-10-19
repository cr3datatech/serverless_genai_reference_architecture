#!/usr/bin/env bash
# The API from the command line: token, models, chat, and one refusal.
#
# Run from the repository root in Bash or Git Bash, with the deploy
# credentials loaded (docs/DEPLOYMENT.md step 2) so the settings can be read
# from Terraform. Needs curl and python (only to read JSON).
#
#   bash examples/curl_examples.sh "Your question" [alias]
#
# Secrets stay in shell variables and are never printed.
set -euo pipefail

PROMPT="${1:-Explain AWS Lambda in two sentences.}"
MODEL="${2:-fast}"

tf() { terraform -chdir=terraform output "$@"; }
pick() { python -c "import sys,json;print(json.load(sys.stdin)['$1'])"; }

API=$(tf -raw api_url)
TOKEN_URL=$(tf -raw token_url)
SCOPE=$(tf -raw oauth_scope)
CLIENT_ID=$(tf -json client_ids | pick demo)
CLIENT_SECRET=$(tf -json client_secrets | pick demo)
API_KEY=$(tf -json api_keys | pick demo)

# 1. OAuth 2.0 client-credentials token, valid 60 minutes. Reuse it.
TOKEN=$(curl -s -d "grant_type=client_credentials&scope=$SCOPE&client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET" "$TOKEN_URL" | pick access_token)

echo "== GET /v1/models"
curl -s -H "Authorization: Bearer $TOKEN" -H "x-api-key: $API_KEY" "$API/v1/models"
echo

echo "== POST /v1/chat ($MODEL)"
BODY=$(python -c "import json,sys;print(json.dumps({'model':sys.argv[1],'max_tokens':300,'messages':[{'role':'user','content':sys.argv[2]}]}))" "$MODEL" "$PROMPT")
curl -s -H "Authorization: Bearer $TOKEN" -H "x-api-key: $API_KEY" -H "content-type: application/json" -d "$BODY" "$API/v1/chat"
echo

echo "== Refusal: no token (expect 401)"
curl -s -w ' [%{http_code}]' -H "x-api-key: $API_KEY" "$API/v1/models"
echo
