#!/bin/sh
# Loads (or reloads) the interview workflow into n8n and switches it on.
# Stop n8n first (Ctrl+C), run:  sh n8n/load_workflow.sh   then start n8n again with: sh n8n/start_n8n.sh
# Note: reloading clears the workflow's test data (outbox, simulated calendar, log).

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$HOME/.local/node/bin:$PATH"
export N8N_USER_FOLDER="$HOME/.local/n8n-data" N8N_DIAGNOSTICS_ENABLED=false GENERIC_TIMEZONE="Europe/London"
N8N="$HOME/.local/n8n-app/node_modules/.bin/n8n"

"$HERE/.venv/bin/python" "$HERE/n8n/build_workflow.py"
"$N8N" import:workflow --input="$HERE/n8n/interview_workflow.json"
"$N8N" publish:workflow --id=rsInterviewFlow1
