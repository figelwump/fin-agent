from fin_cli.fin_extract.parsers.pdf_loader import load_pdf_document_with_engine
from fin_cli.fin_extract.extractors.chase import ChaseExtractor

# Load with both engines
doc_docling = load_pdf_document_with_engine("statements/chase-credit-20240106-statements-6033-.pdf", engine="docling")
doc_pdfplumber = load_pdf_document_with_engine("statements/chase-credit-20240106-statements-6033-.pdf", engine="pdfplumber")

# Test extraction
extractor = ChaseExtractor()

print(f"\n=== DOCLING ===")
print(f"Number of tables: {len(doc_docling.tables)}")
for i, table in enumerate(doc_docling.tables):
    print(f"\nTable {i}:")
    print(f"  Headers ({len(table.headers)} cols): {table.headers}")
    print(f"  Rows: {len(table.rows)}")
    if table.rows:
        print(f"  First row: {table.rows[0][:3] if len(table.rows[0]) > 3 else table.rows[0]}")

print(f"\n\n=== PDFPLUMBER ===")
print(f"Number of tables: {len(doc_pdfplumber.tables)}")

# Find the transactions table in pdfplumber
for i, table in enumerate(doc_pdfplumber.tables):
    if len(table.rows) > 30:  # The big transactions table
        print(f"\nPDFPLUMBER TRANSACTIONS TABLE (Table {i}):")
        print(f"  Headers ({len(table.headers)} cols): {table.headers}")
        print(f"  Rows: {len(table.rows)}")
        print(f"  First 5 rows:")
        for j, row in enumerate(table.rows[:5]):
            print(f"    {j}: {row}")

print(f"\n\n=== DOCLING TABLE 4 & 5 DETAILS ===")
table4 = doc_docling.tables[4]
table5 = doc_docling.tables[5]

print(f"\nTable 4 (40 rows):")
print(f"  Headers: {table4.headers}")
print(f"  Rows 0-5:")
for i, row in enumerate(table4.rows[:6]):
    print(f"    {i}: {row}")

print(f"\nTable 5 (3 rows):")
print(f"  Headers: {table5.headers}")
print(f"  All rows:")
for i, row in enumerate(table5.rows):
    print(f"    {i}: {row}")

print(f"\n\n=== NORMALIZATION TEST ===")
from fin_cli.fin_extract.utils import normalize_pdf_table
from fin_cli.fin_extract.extractors.chase import _chase_header_predicate

# Check Table 4 specifically
table4_normalized = normalize_pdf_table(doc_docling.tables[4], header_predicate=_chase_header_predicate)
print(f"Table 4 normalized:")
print(f"  Headers: {table4_normalized.headers}")
print(f"  Data rows: {len(table4_normalized.rows)}")
print(f"  First 3 data rows:")
for i, row in enumerate(table4_normalized.rows[:3]):
    print(f"    {i}: {row}")

for i, table in enumerate(doc_docling.tables):
    normalized = normalize_pdf_table(table, header_predicate=_chase_header_predicate)
    mapping = extractor._find_column_mapping(normalized.headers)
    if mapping:
        print(f"\nTable {i} - MATCHED!")
        print(f"  Normalized headers: {normalized.headers}")
        print(f"  Mapping: date={mapping.date_index}, desc={mapping.description_index}, amt={mapping.amount_index}")
        print(f"  Data rows: {len(normalized.rows)}")

print(f"\n\n=== EXTRACTION TEST ===")
result_docling = extractor.extract(doc_docling)
print(f"Docling extracted: {len(result_docling.transactions)} transactions")
if result_docling.transactions:
    print("First 3 transactions:")
    for txn in result_docling.transactions[:3]:
        print(f"  {txn.date} | {txn.merchant} | ${txn.amount}")
