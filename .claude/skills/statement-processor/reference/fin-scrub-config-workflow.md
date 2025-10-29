# Fin-Scrub Configuration Workflow

Use this playbook whenever `fin-scrub` needs tweaks for a new institution or the default placeholders are missing PII tokens. The goal is to iterate safely inside the per-statement workspace, then promote deliberate changes into the shared config only after review.

## When to Trigger The Workflow
- **Subtle failures (most common):** The scrubbed text still parses, but sample charges show raw names, addresses, etc. Raise the issue to the user and ask whether to improve scrubbing.
- **Catastrophic failures:** `fin-scrub` exits with an error or emits an empty/garbled file. In this case automatically enter this workflow, flag the failure in the summary, and continue only after the override is in place.

## Step 1 – Bootstrap a Workspace Override
Always work inside the slug workspace (`$WORKDIR = ~/.finagent/skills/statement-processor/<slug>`). Keep overrides here so they can be inspected or discarded alongside other artifacts.

```bash
mkdir -p "$WORKDIR"
source .venv/bin/activate
python - <<'PY'
from importlib import resources
from pathlib import Path

target = Path("$WORKDIR/fin-scrub-overrides.yaml")
if target.exists():
    raise SystemExit("Override already exists; edit the existing file.")
payload = resources.files("fin_cli.fin_scrub").joinpath("default_config.yaml").read_text()
target.write_text(payload)
print(f"Wrote {target}")
PY
```

The override starts as a copy of the bundled defaults. Edit it with your preferred tool. Add concise comments near each new rule explaining the institution-specific quirk so future agents understand why it exists.

## Step 2 – Add New Rules
- Extend `custom_regex` for deterministic placeholders. Use descriptive `stat` names (`CHASE_COBRAND_CUSTOMER_ID`) so redaction counts stay readable.
- Adjust `placeholders` or `detectors` only when defaults are insufficient.
- When handling last-4 digits, prefer the existing `ACCOUNT_LAST4`/`CARD_NUMBER_LAST4` placeholders so downstream tooling keeps metadata.
- Keep whitespace/indentation consistent with YAML two-space nesting.

## Step 3 – Test With The Override
Run `fin-scrub` against the problematic statement using the new config:

```bash
source .venv/bin/activate
fin-scrub statement.pdf \
  --output-dir "$WORKDIR" \
  --config "$WORKDIR/fin-scrub-overrides.yaml" \
  --report
```

Inspect the resulting `scrubbed/` file before continuing the skill loop. Verify that:
- Sensitive tokens are masked with the expected placeholders.
- Transaction rows still resemble the original layout (dates, merchants, amounts intact).
- The `--report` output shows redaction counts for new `stat` keys.

If issues remain, iterate on the override file and rerun the command. Use git diffs or `rg` inside `$WORKDIR` to locate stubborn leakage.

## Step 4 – Decide Whether To Promote
Once the override works:
1. Present a summary of the failure and fixes to the user, including the diff between the override and the bundled defaults:
   ```bash
   diff -u fin_cli/fin_scrub/default_config.yaml "$WORKDIR/fin-scrub-overrides.yaml"
   ```
2. Ask whether to append the new rules to the persistent user config (`~/.finagent/fin-scrub.yaml`). Only proceed with explicit approval.
3. If approved, append **only** the necessary snippets (usually new `custom_regex` entries) and keep the explanatory comments.

Remember that `fin_cli.fin_scrub.main` loads config in this order:
1. Bundled defaults (`fin_cli/fin_scrub/default_config.yaml`)
2. User overrides (`~/.finagent/fin-scrub.yaml`)
3. CLI `--config` file (your workspace override)

Anything copied into the home file applies globally to future runs, so keep it tidy and well-commented.

## Cleanup
- Keep the workspace override alongside other artifacts until the statement is processed. It documents what changed for this session.
- After promotion (or if the user declines), note the outcome in your handoff summary so the next agent knows whether a global update exists.

By isolating experimentation in `$WORKDIR` and annotating each change, we preserve reproducibility, make global updates auditable, and help future agents understand why specific scrub rules exist.
