#!/bin/sh
# Starts n8n on this Mac for the interview-scheduling workflow.
# Run with:  sh n8n/start_n8n.sh      then open http://localhost:5678
# Stop with Ctrl+C.
#
# n8n and Node.js live in ~/.local (installed for this project); n8n's own data in ~/.local/n8n-data.

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$HOME/.local/node/bin:$PATH"

# The shared secret from .streamlit/secrets.toml (never printed, never committed).
INTERVIEW_SECRET="$("$HERE/.venv/bin/python" -c "import tomllib; print(tomllib.load(open('$HERE/.streamlit/secrets.toml','rb'))['N8N_SECRET'])")"
export INTERVIEW_SECRET

export N8N_USER_FOLDER="$HOME/.local/n8n-data"   # n8n's own database and settings
export GENERIC_TIMEZONE="Europe/London"          # interview slots are UK working hours
export TZ="Europe/London"
export N8N_BLOCK_ENV_ACCESS_IN_NODE=false        # lets the workflow read INTERVIEW_SECRET (and nothing is printed)
export NODE_FUNCTION_ALLOW_BUILTIN=crypto        # the workflow signs and checks links with Node's crypto
export N8N_DIAGNOSTICS_ENABLED=false             # no usage data sent to n8n
export N8N_PERSONALIZATION_ENABLED=false
export N8N_VERSION_NOTIFICATIONS_ENABLED=false
export N8N_HOST=localhost N8N_PORT=5678 N8N_PROTOCOL=http
export WEBHOOK_URL="http://localhost:5678/"

exec "$HOME/.local/n8n-app/node_modules/.bin/n8n" start
