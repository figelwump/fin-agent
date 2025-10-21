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
3. Send the prompt to your LLM (Claude, etc.) and save the CSV response (e.g., `llm-output.csv`).
4. Enrich CSV with hashes: `python skills/statement-processor/postprocess.py --input llm-output.csv --output llm-enriched.csv`
5. Import validated rows: `fin-edit import-transactions llm-enriched.csv`

Batch Workflow
1. Scrub all PDFs (use a loop) into `*-scrubbed.txt` files.
2. Build a batch prompt with chunking when needed: `python skills/statement-processor/preprocess.py --batch --input *-scrubbed.txt --max-merchants 150 --max-statements-per-prompt 3 --output batch-prompt.txt`
3. Run the LLM once per emitted prompt chunk and save each CSV response (e.g., `chunk-1.csv`).
4. Post-process every CSV: `python skills/statement-processor/postprocess.py --input chunk-1.csv --output chunk-1-enriched.csv`
5. Concatenate or import each enriched CSV via `fin-edit`.

Working Directory
- Create a dedicated run directory per statement batch, for example `~/.finagent/workflows/statement-processor/<timestamp>/`.
- Store scrubbed statements, prompts, raw LLM CSVs, and enriched CSVs inside that directory so artifacts stay isolated from project source.
- Clean up temporary files once the import is committed to the database.

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

Reference Material (to be refreshed)
- `examples/llm-extraction.md` – full end-to-end example (pending update).
- `examples/batch-processing.md` – legacy content; rewrite to match the LLM pipeline.
- `examples/pipe-mode.md` – legacy content; either retire or adapt for preprocess/postprocess helpers.
- `reference/csv-format.md` – upcoming canonical schema guide for enriched CSVs.

Next Steps for Agents
- Ensure enriched CSVs include `account_key` and `fingerprint` before import.
- Capture review notes for low-confidence rows; feed corrections back into prompt parameters when retrying.
- Report recurring merchant/category gaps so the taxonomy can be extended via rules or prompt tweaks.
