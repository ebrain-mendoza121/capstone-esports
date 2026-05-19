"""
import_matchups_batched.py

Splits matchup_data_derived.csv into chunks of BATCH_SIZE rows and
POSTs each chunk to /matchups/import/csv?overwrite=true sequentially.
Retries each chunk up to MAX_RETRIES times on transient errors.
"""

import csv
import io
import time
import requests
import sys

CSV_PATH   = "matchup_data_derived.csv"
HOST       = "https://capstone-esports-production-5631.up.railway.app"
ENDPOINT   = f"{HOST}/matchups/import/csv?overwrite=true"
BATCH_SIZE = 500
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds between retries

def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        rows = list(reader)
    return headers, rows

def chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i+size]

def rows_to_csv_bytes(headers, rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")

def main():
    headers, all_rows = read_csv(CSV_PATH)
    total = len(all_rows)
    batches = list(chunk(all_rows, BATCH_SIZE))
    print(f"Total rows: {total} | Batch size: {BATCH_SIZE} | Batches: {len(batches)}\n")

    total_imported = 0
    total_skipped  = 0
    total_invalid  = 0
    failed_batches = []

    for i, batch in enumerate(batches, 1):
        print(f"Batch {i}/{len(batches)} ({len(batch)} rows)...", end=" ", flush=True)

        csv_bytes = rows_to_csv_bytes(headers, batch)
        success = False

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.post(
                    ENDPOINT,
                    files={"file": ("batch.csv", csv_bytes, "text/csv")},
                    timeout=60,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    total_imported += data.get("imported", 0)
                    total_skipped  += data.get("skipped_duplicates", 0)
                    total_invalid  += data.get("invalid_rows", 0)
                    print(f"✅ imported={data.get('imported',0)} skipped={data.get('skipped_duplicates',0)} invalid={data.get('invalid_rows',0)}")
                    success = True
                    break
                else:
                    print(f"⚠ HTTP {resp.status_code} (attempt {attempt}/{MAX_RETRIES})", end=" ")
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY)
            except Exception as e:
                print(f"⚠ Error: {e} (attempt {attempt}/{MAX_RETRIES})", end=" ")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)

        if not success:
            print(f"❌ FAILED after {MAX_RETRIES} attempts")
            failed_batches.append(i)

        # Small delay between batches to avoid overwhelming Supabase pool
        time.sleep(0.5)

    print(f"\n{'='*50}")
    print(f"DONE")
    print(f"  Total imported:  {total_imported}")
    print(f"  Total skipped:   {total_skipped}")
    print(f"  Total invalid:   {total_invalid}")
    if failed_batches:
        print(f"  Failed batches:  {failed_batches}")
        print("  Re-run this script to retry — skipped_duplicates will handle already-imported rows.")
    else:
        print(f"  All batches succeeded ✅")

    print(f"\nNow retrain the matchup model:")
    print(f'  curl -X POST "{HOST}/ai/train/matchup-predictor"')

if __name__ == "__main__":
    main()
