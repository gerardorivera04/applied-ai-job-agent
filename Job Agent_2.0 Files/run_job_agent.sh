#!/bin/bash
# Wrapper for cron: loads your env vars, activates any venv if present,
# runs the agent, and logs output with a timestamp.
#
# Usage in crontab (see README.md for full instructions):
#   0 7 * * 1-5 /path/to/job_agent/run_job_agent.sh
#
# IMPORTANT: cron runs with almost no environment set. This script
# expects your secrets to be in a file called `.env` in this same
# directory (see .env.example) -- it will NOT inherit your shell's
# exported variables when run by cron.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load secrets from .env if present
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  source "$SCRIPT_DIR/.env"
  set +a
fi

# If you use a virtualenv, uncomment and adjust:
# source "$SCRIPT_DIR/venv/bin/activate"

LOG_FILE="$SCRIPT_DIR/run.log"
echo "===== Run started: $(date) =====" >> "$LOG_FILE"
python3 "$SCRIPT_DIR/job_agent.py" >> "$LOG_FILE" 2>&1
echo "===== Run finished: $(date) =====" >> "$LOG_FILE"
