#!/usr/bin/env bash
# Unattended Claude Code run with hard caps (planning/agentic-engineering.md item 46).
# Usage: tools/agent-run.sh <budget-usd> <max-turns> "<brief>"
# The client budget resets on --continue/--resume: never resume an unattended run.
# Only the Console workspace spend limit is a real ceiling.
set -uo pipefail
budget="${1:?budget in USD}"; turns="${2:?max turns}"; brief="${3:?brief}"
cap=$(python -c "print(round(float('$budget') * 0.8, 2))")  # 80% of the target
exec claude -p "$brief" --max-budget-usd "$cap" --max-turns "$turns" \
  --permission-prompts none --output-format json
