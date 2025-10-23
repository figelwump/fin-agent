#!/usr/bin/env bash
# Batch helper for statement-processor skill.
# Automates steps 1 & 2 of the documented workflow:
#   1. Scrub PDFs into `*-scrubbed.txt`
#   2. Build batch prompts via preprocess.py
# Remaining steps (LLM invocation, post-processing, imports) stay manual.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_MAX_MERCHANTS=150
DEFAULT_MAX_STATEMENTS=3
DEFAULT_MIN_MERCHANT_COUNT=1
CLEAN_SCRUBBED=1
WORKDIR=""
MAX_MERCHANTS="$DEFAULT_MAX_MERCHANTS"
MAX_STATEMENTS="$DEFAULT_MAX_STATEMENTS"
MIN_MERCHANT_COUNT="$DEFAULT_MIN_MERCHANT_COUNT"
CATEGORIES_ONLY=0
CATEGORIES_LIMIT=""
declare -a PDF_INPUTS=()

usage() {
  cat <<'EOF'
Usage: run_batch.sh [options] <pdf>...

Options:
  --workdir PATH                 Working directory for artifacts. Defaults to ~/.finagent/skills/statement-processor/<timestamp>.
  --max-merchants N              Limit merchant taxonomy size (default: 150).
  --max-statements-per-prompt N  Chunk size for prompts (default: 3).
  --min-merchant-count N         Minimum occurrences required to include merchant (default: 1).
  --categories-only              Skip merchant taxonomy (pass-through to preprocess.py).
  --categories-limit N           Limit number of categories included.
  --no-clean                     Preserve existing *-scrubbed.txt files in workdir.
  -h, --help                     Show this help.

Example:
  ./run_batch.sh --max-merchants 200 statements/*.pdf

Notes:
  - Activate the project virtualenv before running (`source .venv/bin/activate`).
  - The script stops if any scrub or prompt generation fails.
EOF
}

timestamp_workdir() {
  local ts
  ts="$(date +"%Y%m%d-%H%M%S")"
  printf "%s/.finagent/skills/statement-processor/%s" "$HOME" "$ts"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --workdir)
        [[ $# -lt 2 ]] && { echo "Missing value for --workdir" >&2; exit 1; }
        WORKDIR="$2"
        shift 2
        ;;
      --max-merchants)
        [[ $# -lt 2 ]] && { echo "Missing value for --max-merchants" >&2; exit 1; }
        MAX_MERCHANTS="$2"
        shift 2
        ;;
      --max-statements-per-prompt)
        [[ $# -lt 2 ]] && { echo "Missing value for --max-statements-per-prompt" >&2; exit 1; }
        MAX_STATEMENTS="$2"
        shift 2
        ;;
      --min-merchant-count)
        [[ $# -lt 2 ]] && { echo "Missing value for --min-merchant-count" >&2; exit 1; }
        MIN_MERCHANT_COUNT="$2"
        shift 2
        ;;
      --categories-only)
        CATEGORIES_ONLY=1
        shift
        ;;
      --categories-limit)
        [[ $# -lt 2 ]] && { echo "Missing value for --categories-limit" >&2; exit 1; }
        CATEGORIES_LIMIT="$2"
        shift 2
        ;;
      --no-clean)
        CLEAN_SCRUBBED=0
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      --)
        shift
        while [[ $# -gt 0 ]]; do
          PDF_INPUTS+=("$1")
          shift
        done
        ;;
      -*)
        echo "Unknown option: $1" >&2
        usage
        exit 1
        ;;
      *)
        PDF_INPUTS+=("$1")
        shift
        ;;
    esac
  done
}

validate_args() {
  if [[ ${#PDF_INPUTS[@]} -eq 0 ]]; then
    echo "No PDF inputs supplied." >&2
    usage
    exit 1
  fi
  for pdf in "${PDF_INPUTS[@]}"; do
    if [[ ! -f "$pdf" ]]; then
      echo "PDF not found: $pdf" >&2
      exit 1
    fi
  done
}

prepare_workdir() {
  if [[ -z "$WORKDIR" ]]; then
    WORKDIR="$(timestamp_workdir)"
    echo "No --workdir provided. Using $WORKDIR"
  fi
  WORKDIR="$(python -c 'import os, sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$WORKDIR")"
  SCRUBBED_DIR="$WORKDIR/scrubbed"
  mkdir -p "$SCRUBBED_DIR"
  if [[ "$CLEAN_SCRUBBED" -eq 1 ]]; then
    find "$SCRUBBED_DIR" -type f -name '*-scrubbed.txt' -delete 2>/dev/null || true
  fi
  mkdir -p "$WORKDIR/raw"
  mkdir -p "$WORKDIR/prompts"
}

scrub_pdfs() {
  echo "Scrubbing PDF statements..."
  local idx=0
  for pdf in "${PDF_INPUTS[@]}"; do
    idx=$((idx + 1))
    local abs_pdf
    abs_pdf="$(python -c 'import os, sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$pdf")"
    local base
    base="$(basename "$abs_pdf")"
    local stem="${base%.*}"
    local scrubbed_path="$WORKDIR/scrubbed/${stem}-scrubbed.txt"
    echo "  [$idx/${#PDF_INPUTS[@]}] fin-scrub $abs_pdf -> $scrubbed_path"
    fin-scrub "$abs_pdf" --output "$scrubbed_path"
  done
}

build_prompts() {
  local preprocess="$SCRIPT_DIR/preprocess.py"
  if [[ ! -f "$preprocess" ]]; then
    echo "Cannot locate preprocess.py at $preprocess" >&2
    exit 1
  fi
  local -a SCRUBBED_FILES=()
  while IFS= read -r scrubbed_file; do
    SCRUBBED_FILES+=("$scrubbed_file")
  done < <(find "$WORKDIR/scrubbed" -maxdepth 1 -type f -name '*-scrubbed.txt' | sort)
  if [[ ${#SCRUBBED_FILES[@]} -eq 0 ]]; then
    echo "No scrubbed statements found in $WORKDIR/scrubbed" >&2
    exit 1
  fi
  echo "Generating prompts via preprocess.py..."
  PREPROCESS_CMD=(python "$preprocess" --batch --output-dir "$WORKDIR")
  if [[ -n "$MAX_MERCHANTS" ]]; then
    PREPROCESS_CMD+=(--max-merchants "$MAX_MERCHANTS")
  fi
  if [[ -n "$MAX_STATEMENTS" ]]; then
    PREPROCESS_CMD+=(--max-statements-per-prompt "$MAX_STATEMENTS")
  fi
  if [[ -n "$MIN_MERCHANT_COUNT" ]]; then
    PREPROCESS_CMD+=(--min-merchant-count "$MIN_MERCHANT_COUNT")
  fi
  if [[ "$CATEGORIES_ONLY" -eq 1 ]]; then
    PREPROCESS_CMD+=(--categories-only)
  fi
  if [[ -n "$CATEGORIES_LIMIT" ]]; then
    PREPROCESS_CMD+=(--categories-limit "$CATEGORIES_LIMIT")
  fi
  for scrubbed in "${SCRUBBED_FILES[@]}"; do
    PREPROCESS_CMD+=(--input "$scrubbed")
  done
  "${PREPROCESS_CMD[@]}"
}

summarize() {
  echo
  echo "Batch preparation complete."
  echo "Workspace: $WORKDIR"
  echo "Scrubbed statements:"
  find "$WORKDIR/scrubbed" -maxdepth 1 -type f -name '*-scrubbed.txt' -print | sed 's/^/  - /'
  echo "Prompt chunks:"
  if [[ -d "$WORKDIR/prompts" ]]; then
    find "$WORKDIR/prompts" -maxdepth 1 -type f -name '*.txt' | sort | sed 's/^/  - /' || true
  else
    echo "  (none found)"
  fi
  cat <<EOF

Next steps:
  1. Run the LLM over each prompt in the order emitted above and save the CSV responses.
  2. Post-process each CSV with postprocess.py.
  3. Review/import transactions via fin-edit.
EOF
}

main() {
  parse_args "$@"
  validate_args
  prepare_workdir
  scrub_pdfs
  build_prompts
  summarize
}

main "$@"
