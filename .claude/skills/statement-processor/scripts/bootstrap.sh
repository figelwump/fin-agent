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
LABEL=""
SESSION_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --session|--workspace|--slug)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for $1" >&2
        exit 1
      fi
      SESSION_ID="$2"
      shift 2
      ;;
    --help|-h)
      cat <<'EOF'
Usage: bootstrap.sh [label] [--session <slug>]

Arguments:
  label            Optional human-friendly label (used only when --session is absent).

Options:
  --session <slug> Provide an explicit workspace slug; disables automatic timestamping so
                   multiple skills can share the same directory.
  -h, --help       Show this message.
EOF
      exit 0
      ;;
    *)
      if [[ -n "$LABEL" ]]; then
        echo "Unexpected argument: $1" >&2
        exit 1
      fi
      LABEL="$1"
      shift
      ;;
  esac
done

if [[ -z "${SESSION_ID}" && -n "${SESSION_SLUG:-}" ]]; then
  SESSION_ID="${SESSION_SLUG}"
fi

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

SESSION_VALUE=""
if [[ -n "${SESSION_ID}" ]]; then
  SAFE_SESSION="$(sanitise "${SESSION_ID}")"
  if [[ -z "${SAFE_SESSION}" ]]; then
    echo "Invalid session slug provided to --session" >&2
    exit 1
  fi
  SESSION_VALUE="${SAFE_SESSION}"
elif [[ -n "${LABEL}" ]]; then
  SAFE_LABEL="$(sanitise "${LABEL}")"
  if [[ -z "${SAFE_LABEL}" ]]; then
    SAFE_LABEL="run"
  fi
  SESSION_VALUE="${SAFE_LABEL}-${TIMESTAMP}"
else
  SESSION_VALUE="${TIMESTAMP}"
fi

RUN_DIR="${ROOT}/${SESSION_VALUE}"

SCRUBBED_DIR="${RUN_DIR}/scrubbed"
PROMPTS_DIR="${RUN_DIR}/prompts"
LLM_DIR="${RUN_DIR}/llm"
ENRICHED_DIR="${RUN_DIR}/enriched"

mkdir -p "${SCRUBBED_DIR}" "${PROMPTS_DIR}" "${LLM_DIR}" "${ENRICHED_DIR}"

cat <<EOF
export SESSION_SLUG="${SESSION_VALUE}"
export FIN_STATEMENT_WORKDIR="${RUN_DIR}"
export FIN_STATEMENT_SCRUBBED_DIR="${SCRUBBED_DIR}"
export FIN_STATEMENT_PROMPTS_DIR="${PROMPTS_DIR}"
export FIN_STATEMENT_LLM_DIR="${LLM_DIR}"
export FIN_STATEMENT_ENRICHED_DIR="${ENRICHED_DIR}"
echo "Statement processor workspace initialised at ${RUN_DIR}"
EOF
