# Batch Processing

Environment
- `source .venv/bin/activate`

Extract all PDFs
```bash
for pdf in ~/Downloads/statements/*.pdf; do
  base=$(basename "$pdf" .pdf)
  fin-extract "$pdf" --output "~/fin-data/$base.csv"
done
```

Import all CSVs (choose one)
```bash
# Option A: fin-import (if available)
fin-import ~/fin-data/*.csv

# Option B: fin-enhance in rules-only mode
fin-enhance ~/fin-data/*.csv --skip-llm
```

Pipe Mode (no intermediate files)
```bash
for pdf in ~/Downloads/statements/*.pdf; do
  fin-extract "$pdf" --stdout
done | fin-enhance --stdin --skip-llm
```

