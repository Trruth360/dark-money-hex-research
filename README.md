# Dark Money Research + Hex

This project is a starter workflow for bringing dark money research data into Hex for cleaning, calculations, visual exploration, and dashboarding.

It is designed for the common research stack:
- CSV files from campaign finance, nonprofit filings, or research exports
- SQL-based rollups in Hex
- Python-based enrichment and standardization
- charts and dashboards for donor flow, recipient totals, and time series

## What is included

- `requirements.txt` – Python dependencies
- `src/dark_money_hex.py` – data loading and aggregation pipeline
- `sql/hex_queries.sql` – example Hex SQL cells
- `data/sample_dark_money_transactions.csv` – realistic mock dataset

## Typical research questions this supports

- Which donors are sending the largest total amounts?
- Which recipients receive the most funding over time?
- Which donor-to-recipient paths are largest?
- How do flows change month to month?
- Which recipients are tied to a cluster of related entities?

## Recommended Hex workflow

1. Upload your CSV into Hex.
2. Create a Python cell to run the preprocessing code from `src/dark_money_hex.py`.
3. Create a SQL cell to query the cleaned tables.
4. Build charts such as:
   - stacked bar of monthly totals
   - top donor table
   - recipient ranking
   - network graph or sankey by donor/recipient path

## Example usage

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the data prep script:

```bash
python src/dark_money_hex.py
```

This will generate ready-to-import CSV outputs in the `data/outputs/` directory.

## Mock data schema

The sample dataset includes these fields:

- `transaction_id`
- `transaction_date`
- `donor_name`
- `donor_type`
- `recipient_name`
- `recipient_type`
- `amount_usd`
- `filer`
- `state`
- `entity_class`
- `transaction_type`
- `source`
- `notes`

## Hex SQL examples

You can paste query patterns from `sql/hex_queries.sql` into a Hex SQL cell after your imported table is available.

## Notes

This is intentionally generic and research-friendly rather than legal/ethical advice. If you are doing actual public-interest or investigative analysis, make sure your data provenance, source attribution, and legal compliance are documented.

---

For production use, you can replace the sample CSV with your real data and adapt the grouping logic to your database schema or API payloads.
