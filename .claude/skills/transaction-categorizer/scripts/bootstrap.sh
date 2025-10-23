#!/usr/bin/env bash
# Workspace bootstrapper for the transaction-categorizer skill.
# Usage:
#   eval "$(/path/to/bootstrap.sh optional-label)"
#
# The script creates a deterministic working directory under
# ~/.finagent/skills/transaction-categorizer (overridable via FIN_CATEGORIZER_ROOT)
# and prints environment exports so callers can `eval` them.

set -euo pipefail

ROOT="${FIN_CATEGORIZER_ROOT:-$HOME/.finagent/skills/transaction-categorizer}"
LABEL="${1:-}"
TIMESTAMP="$(date +"%Y%m%d-%H%M%S")"

sanitise() {
  local raw="$1"
  # Keep alphanumerics, dash, underscore; collapse everything else to hyphen.
  local cleaned
  cleaned="$(echo "$raw" | tr '[:upper:]' '[:lower:]' | tr -cs '[:alnum:]-_' '-')"
  # Trim leading/trailing separators.
  cleaned="$(echo "$cleaned" | sed -e 's/^-*//' -e 's/-*$//')"
  printf '%s' "$cleaned"
}

if [[ -n "${LABEL}" ]]; then
  SAFE_LABEL="$(sanitise "${LABEL}")"
  if [[ -z "${SAFE_LABEL}" ]]; then
    SAFE_LABEL="run"
  fi
  RUN_DIR="${ROOT}/${SAFE_LABEL}-${TIMESTAMP}"
else
  RUN_DIR="${ROOT}/${TIMESTAMP}"
fi

QUERIES_DIR="${RUN_DIR}/queries"
PROMPTS_DIR="${RUN_DIR}/prompts"
LLM_DIR="${RUN_DIR}/llm"

mkdir -p "${QUERIES_DIR}" "${PROMPTS_DIR}" "${LLM_DIR}"

cat <<EOF
export FIN_CATEGORIZER_WORKDIR="${RUN_DIR}"
export FIN_CATEGORIZER_QUERIES_DIR="${QUERIES_DIR}"
export FIN_CATEGORIZER_PROMPTS_DIR="${PROMPTS_DIR}"
export FIN_CATEGORIZER_LLM_DIR="${LLM_DIR}"
echo "Transaction categorizer workspace initialised at ${RUN_DIR}"
EOF
