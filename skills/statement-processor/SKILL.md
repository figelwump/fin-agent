---
name: statement-processor
description: Extract and import bank statements from PDF files into the local SQLite database.
---

# Statement Processor Skill

Teach the agent how to extract and import bank statements end-to-end.

Environment
- Activate the venv before running commands:
  - `source .venv/bin/activate`

Quick Start (LLM Pipeline)
1. Scrub sensitive data: `fin-scrub statement.pdf --output statement-scrubbed.txt`
2. Build prompt with taxonomies: `python skills/statement-processor/preprocess.py --input statement-scrubbed.txt --output prompt.txt`
3. Send prompt to your LLM (Claude, etc.) and capture the CSV response.
4. Enrich CSV with hashes: `python skills/statement-processor/postprocess.py --input llm-output.csv --output llm-enriched.csv`
5. Import validated rows: `fin-edit import-transactions llm-enriched.csv`

Batch Workflow
1. Scrub all PDFs (use a loop) into `*-scrubbed.txt` files.
2. Build a batch prompt with chunking when needed: `python skills/statement-processor/preprocess.py --batch --input *-scrubbed.txt --max-merchants 150 --max-statements-per-prompt 3 --output batch-prompt.txt`
3. Run the LLM once per emitted prompt chunk and save each CSV.
4. Post-process every CSV: `python skills/statement-processor/postprocess.py --input chunk.csv --stdout > chunk-enriched.csv`
5. Concatenate or import each enriched CSV via `fin-edit`.

Handling Low Confidence
- The prompt instructs the LLM to lower `confidence` (<0.7) whenever unsure.
- Review low-confidence rows first; edit merchants/categories before import or after import using `fin-edit`.
- If account metadata is unclear, pause and ask the user which account the statement belongs to; rerun post-processing once metadata is confirmed.

Available Commands
- `fin-scrub`: sanitize PDFs to redact PII.
- `python skills/statement-processor/preprocess.py`: build single or batch prompts with existing taxonomies.
- `python skills/statement-processor/postprocess.py`: append `account_key`/`fingerprint` to LLM CSV output.
- `fin-edit import-transactions`: persist enriched CSV rows into SQLite.
- `fin-query saved merchants --format json --min-count N`: retrieve merchant taxonomy for debugging.

Progressive Disclosure
- `examples/llm-extraction.md` – full end-to-end example (todo).
- `examples/batch-processing.md` – multi-statement workflow (todo).
- `reference/csv-format.md` – definitive list of required columns and hash rules (todo).
- `troubleshooting/extraction-errors.md` – update to cover LLM parsing issues (todo).

Next Steps for Agents
- Ensure enriched CSVs include `account_key` and `fingerprint` before import.
- Capture review notes for low-confidence rows; feed corrections back into prompt parameters when retrying.
- Report any recurring merchant/category gaps so the taxonomy can be extended.
