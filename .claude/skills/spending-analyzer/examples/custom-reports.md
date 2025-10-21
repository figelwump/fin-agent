# Custom Report Assembly

Example: Monthly Summary Report for September 2025

Run analyzers
```bash
fin-analyze spending-trends --month 2025-09 --compare --format json
fin-analyze category-breakdown --month 2025-09 --compare --format json
fin-analyze merchant-frequency --month 2025-09 --min-visits 2 --format json
fin-analyze unusual-spending --month 2025-09 --sensitivity 3 --format json
fin-analyze subscription-detect --month 2025-09 --format json
```

Assemble a narrative summary from the JSON results. Include totals, category shares,
notable changes vs last month, merchants, subscriptions, and anomalies.

