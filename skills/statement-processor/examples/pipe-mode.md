# Pipe Mode (No Intermediate Files)

Environment
- `source .venv/bin/activate`

Stream extraction directly into import (rules-only import shown):
```bash
for pdf in ~/Downloads/statements/*.pdf; do
  fin-extract "$pdf" --stdout
done | fin-enhance --stdin --skip-llm
```

