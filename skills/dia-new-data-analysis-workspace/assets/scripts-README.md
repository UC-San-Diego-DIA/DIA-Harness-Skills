# Pipeline manifest

Keep this file current. One line per script, describing what it reads and what it writes. A script's number is one more than the highest number of anything it reads; independent scripts may share a number.

```text
- 01_load_tables.py - reads Excel exports from data/raw/, writes staging tables
- 02_combine_orders_customers.py - reads 01, writes the combined orders table
- 02_clean_sales.py - reads 01, independent of 02_combine, writes the clean sales table
- 03_build_summary.py - reads both 02 outputs, writes the final summary table
```
