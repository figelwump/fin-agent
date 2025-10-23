# plan_fin_scrub_102025

## Objective
- Build a `fin-scrub` CLI that redacts personally identifiable information (PII) from bank-statement text using deterministic regex passes followed by an open-source PII recognizer (no LLMs yet). Output should preserve layout for downstream parsing while guaranteeing sensitive tokens are masked.

## Phase 1 – Requirements & Design
- [x] Define scope of PII to remove (names, addresses, account/routing numbers, card numbers, emails, phone numbers, SSNs, URLs, etc.) and document masking conventions (e.g., `[ACCOUNT_NUMBER]`).
  - Core tokens: legal names (PERSON), mailing addresses (street/city/state/ZIP), institution account identifiers (full numbers + last-4), routing numbers, card numbers (PAN + virtual), ACH IDs, SSNs/ITINs, EINs, emails, phone numbers, URLs, and customer IDs found in headers/footers.
  - Placeholder scheme (uppercase, underscores): `[NAME]`, `[ADDRESS]`, `[ACCOUNT_NUMBER]`, `[ROUTING_NUMBER]`, `[CARD_NUMBER]`, `[SSN]`, `[PHONE_NUMBER]`, `[EMAIL]`, `[URL]`, `[CUSTOMER_ID]`. Preserve contextual tokens (e.g., `****1234` -> `[ACCOUNT_LAST4:1234]`) when feasible to help downstream reconciliation.
- [x] Evaluate candidate libraries (e.g., Microsoft Presidio, scrubadub, spaCy NER) and decide which to integrate for step 2 entity detection.
  - Decision: use **scrubadub** with the TextBlob name detector; Presidio + spaCy required heavy compiled dependencies in this environment. scrubadub provides lightweight detectors we can augment with custom regex placeholders.
- [x] Specify CLI ergonomics: accept PDF inputs directly (handle conversion to text internally), support `--stdin` raw text mode, define output channel (file/stdout), logging, and extensibility (e.g., allow users to extend regex patterns via config file).
  - CLI contract: `fin-scrub <statement.pdf>` emits scrubbed text to stdout by default; `--output FILE` writes to disk; `--stdin` consumes plain text; `--report` prints counts per PII type to stderr.
  - Internally: use existing PDF loader (`load_pdf_document_with_engine`) to extract text so statement coverage stays aligned with `fin-extract`. Config file (`~/.finagent/fin-scrub.yaml`) can override placeholders or disable recognizers.

## Phase 2 – Implementation
- [x] Scaffold `fin-scrub` CLI entrypoint with Click (consistent with other tools) and wire it into `pyproject.toml` console scripts.
- [x] Implement regex-based scrubbers covering high-confidence patterns (credit-card via Luhn, account/routing numbers, emails, URLs, phone numbers, SSNs, ZIP codes when part of addresses).
- [x] Integrate chosen PII library as a second pass, ensuring it operates on the already-redacted text and respects our placeholder format.
  - Leveraged `scrubadub` detectors (TextBlob name detector + phone/email/credit card) layered after regex stage; added guardrails/skip list to avoid over-scrubbing statement vocabulary. Requires `python -m textblob.download_corpora` once to enable POS tagging.
- [x] Add configuration options to enable/disable specific recognizers and to customize placeholder tokens.
  - Planned YAML schema (`~/.finagent/fin-scrub.yaml` fallback to repo defaults):
    ```yaml
    transaction_markers:
      - type: regex
        pattern: '^\s*\d{1,2}/\d{1,2}\s+\d{1,2}/\d{1,2}\s+'
      - type: regex
        pattern: '^\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2}\b.*\d+\.\d{2}'
    page_reset_markers:
      headers:
        - '\bPage\s*\d+\s*of\s*\d+\b'
      footers:
        - 'continued on next page'
    placeholders:
      NAME: '[NAME]'
      ADDRESS: '[ADDRESS]'
      ACCOUNT_NUMBER: '[ACCOUNT_NUMBER]'
      CARD_NUMBER: '[CARD_NUMBER]'
      ACCOUNT_LAST4: '[ACCOUNT_LAST4:{last4}]'
    detectors:
      scrub_name: true
      scrub_address: true
      scrub_email: true
      scrub_phone: false
    skip_words:
      name:
        - statement
        - payment
        - autopay
    custom_regex:
      - pattern: 'Ach ID:\s*(\d{12})'
        placeholder: '[ACH_ID]'
    ```
  - CLI flag `--config PATH` overrides the default; config is merged with built-ins so LLMs can safely add/remove entries without editing Python.

## Phase 3 – Validation & Documentation
- [ ] Create fixture statements (or sanitized samples) and automated tests verifying that sensitive tokens are replaced while non-PII remains intact.
- [ ] Document usage in README / docs (examples for file and stdin pipelines, notes on false positives/negatives, guidance for extending pattern lists).
- [ ] Benchmark performance on representative statements; capture findings and potential optimizations (e.g., streaming vs. in-memory processing).

## Implementation Notes
- Reuse shared utility modules where practical (e.g., existing Luhn checks). If new helpers are needed, place them under `fin_cli/shared/`.
- Ensure the CLI can function as a filter (`fin-scrub statement.pdf --stdout` after extraction) and on plain text (`fin-scrub --stdin < statement.txt`).
- Consider emitting a redaction report (counts per PII type) via a verbose flag for auditing.
- Keep regex patterns/test fixtures ASCII to align with repo guidelines; placeholders should be uppercase with underscores.
- TextBlob-based name detection requires once-off corpora download (`python -m textblob.download_corpora` plus `nltk.download('punkt_tab')`); document this prerequisite for developers.
