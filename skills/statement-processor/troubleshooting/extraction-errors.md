# Extraction Troubleshooting

"No transactions extracted"
- Cause: unsupported bank/PDF or scanned image
- Try: `fin-extract dev list-plugins`
- Try: `fin-extract <pdf> --engine pdfplumber`

"CSV format invalid"
- Cause: manually edited CSV or old extractor version
- Fix: re-extract from original PDF

Database locked
- Cause: another process using the DB
- Fix: wait or stop the process. Example (macOS): `lsof ~/.finagent/data.db`

