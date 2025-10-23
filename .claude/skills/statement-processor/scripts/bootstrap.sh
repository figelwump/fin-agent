#!/usr/bin/env bash
# Workspace bootstrapper for the statement-processor skill.
# Usage:
#   eval "$(/path/to/bootstrap.sh optional-label)"
#
# The script creates a deterministic working directory under
# ~/.finagent/skills/statement-processor (overridable via FIN_STATEMENT_ROOT)
# and prints environment exports so callers can `eval` them.

set -euo pipefail

ROOT="${FIN_STATEMENT_ROOT:-$HOME/.finagent/skills/statement-processor}"
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

SCRUBBED_DIR="${RUN_DIR}/scrubbed"
PROMPTS_DIR="${RUN_DIR}/prompts"
LLM_DIR="${RUN_DIR}/llm"
ENRICHED_DIR="${RUN_DIR}/enriched"

mkdir -p "${SCRUBBED_DIR}" "${PROMPTS_DIR}" "${LLM_DIR}" "${ENRICHED_DIR}"

cat <<EOF
export FIN_STATEMENT_WORKDIR="${RUN_DIR}"
export FIN_STATEMENT_SCRUBBED_DIR="${SCRUBBED_DIR}"
export FIN_STATEMENT_PROMPTS_DIR="${PROMPTS_DIR}"
export FIN_STATEMENT_LLM_DIR="${LLM_DIR}"
export FIN_STATEMENT_ENRICHED_DIR="${ENRICHED_DIR}"
echo "Statement processor workspace initialised at ${RUN_DIR}"
EOF
