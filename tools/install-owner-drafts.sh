#!/usr/bin/env bash
# Install the reviewed drafts that agents may not write (protect-paths gate, item 13).
# Run by Manoj only, from the repo root, then review `git diff` and commit by hand.
#   bash tools/install-owner-drafts.sh
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1
mkdir -p .github/workflows .claude/hooks .claude/agents
cp planning/ci/workflows/*.yml .github/workflows/
[ -f .github/workflows/ci.yml ] && git rm -q .github/workflows/ci.yml   # replaced by pr.yml
cp planning/claude-drafts/hooks/gate.py planning/claude-drafts/hooks/trim_output.py .claude/hooks/
cp planning/claude-drafts/agents/*.md .claude/agents/
cp planning/claude-drafts/settings.json .claude/settings.json
git status --short .github .claude
echo "Installed. Review with: git diff -- .github .claude ; then commit by hand."
echo "Repository secret needed by review.yml: CLAUDE_CODE_OAUTH_TOKEN (claude setup-token)."
echo "Repository variable needed by main.yml: PRODUCTION_HEALTH_URL."
