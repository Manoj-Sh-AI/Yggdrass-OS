#!/usr/bin/env bash
# Thin wrapper: the logic is in gate.py (one place, tested). NOT set -e.
set -uo pipefail
exec python "$(dirname "$0")/gate.py" full-suite
