"""Ingest Santander Product Recommendation data: Kaggle competition -> GCS (raw) -> BigQuery (raw).

Env-driven so it runs identically on your local machine, in Google Cloud Shell
(recommended: keeps the ~700 MB zip off your laptop), or inside a Cloud Run Job
wrapped by Airflow later. Reads config from environment (see .env.example).

Idempotent: skips the download if the object already exists in GCS, and replaces
the BigQuery table on load (WRITE_TRUNCATE).

Source: Santander Product Recommendation Kaggle competition (2016).
~13.6M monthly snapshots of ~950k customers (Jan 2015 - May 2016).
Non-commercial/educational/portfolio use only; raw data NOT redistributed.
Accept competition rules at https://www.kaggle.com/c/santander-product-recommendation
under matirvazques@gmail.com before running this script.

Auth: uses Kaggle's current API token (KGAT_...) as a bearer token against the REST
API — the pip `kaggle`/`kagglehub` libraries only support the legacy username+key.
Provide it via KAGGLE_API_TOKEN or ~/.kaggle/access_token (see README / .env.example).

Run:
    pip install -r scripts/requirements.txt
    python scripts/ingest.py
"""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

from google.cloud import bigquery, storage


def env(key: str, default: str | None = None) -> str:
    val = os.environ.get(key, default)
    if val is None:
        sys.exit(f"Missing required env var: {key} (see .env.example)")
    return val


KAGGLE_API_BASE = "https://www.kaggle.com/api/v1"


def read_kaggle_token() -> str:
    """Kaggle's current API token (KGAT_...), read from env or ~/.kaggle/access_token.

    The pip `kaggle`/`kagglehub` libraries still only support the legacy
    username+key credential; this project uses the newer bearer token, so we call
    the REST API directly (see download_from_kaggle_competition).
    """
    token = os.environ.get("KAGGLE_API_TOKEN")
    if token:
        return token.strip()
    token_file = Path.home() / ".kaggle" / "access_token"
    if token_file.exists():
        return token_file.read_text().strip()
    sys.exit(
        "No Kaggle API token found. Set KAGGLE_API_TOKEN or write the token to "
        "~/.kaggle/access_token (see README)."
    )


def download_from_kaggle_competition(competition: str, file_name: str, dest_dir: Path) -> Path:
    """Download one competition file via the Kaggle REST API (bearer token), unzip it.

    Kaggle serves competition CSVs as `<file_name>.zip`; the download endpoint 302-
    redirects to a signed GCS URL. `requests` strips the Authorization header on the
    cross-host redirect, so the bearer token is only ever sent to kaggle.com.
    """
    import requests

    token = read_kaggle_token()
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / f"{file_name}.zip"
    csv_path = dest_dir / file_name

    url = f"{KAGGLE_API_BASE}/competitions/data/download/{competition}/{file_name}.zip"
    print(f"Downloading {file_name}.zip from kaggle competition: {competition} ...")
    with requests.get(
        url, headers={"Authorization": f"Bearer {token}"}, stream=True, timeout=600
    ) as resp:
        if resp.status_code == 401:
            sys.exit("Kaggle returned 401 — token invalid or competition rules not accepted.")
        resp.raise_for_status()
        with open(zip_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)

    print(f"Unzipping {zip_path.name} ...")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    zip_path.unlink()

    if not csv_path.exists():
        sys.exit(f"Expected {csv_path} after extraction but it is missing.")

    return csv_path


def upload_to_gcs(local_path: Path, bucket_name: str, blob_name: str) -> str:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    if blob.exists():
        print(f"gs://{bucket_name}/{blob_name} already exists — skipping upload.")
    else:
        print(f"Uploading to gs://{bucket_name}/{blob_name} ...")
        blob.upload_from_filename(str(local_path))
    return f"gs://{bucket_name}/{blob_name}"


def read_gcs_header(bucket_name: str, blob_name: str) -> list[str]:
    """Read the CSV header row from GCS (first 64 KB) and return column names."""
    client = storage.Client()
    blob = client.bucket(bucket_name).blob(blob_name)
    head = blob.download_as_bytes(start=0, end=65535).decode("utf-8", errors="replace")
    header_line = head.splitlines()[0]
    return [c.strip().strip('"') for c in header_line.split(",")]


def load_into_bigquery(
    gcs_uri: str, project: str, dataset: str, table: str, location: str, max_bad_records: int
) -> None:
    client = bigquery.Client(project=project)
    dataset_ref = bigquery.Dataset(f"{project}.{dataset}")
    dataset_ref.location = location
    client.create_dataset(dataset_ref, exists_ok=True)

    # Every raw column is loaded as STRING and cast in dbt staging. The Santander
    # panel mixes formats within columns (age/antiguedad/renta carry leading spaces,
    # "NA" placeholders, and decimals), so BigQuery type autodetection fails part-way
    # through the file. Loading raw-as-text is the reproducible, honest approach: the
    # raw layer preserves the source verbatim and stg_customer_month owns all casting.
    bucket_name, _, blob_name = gcs_uri.removeprefix("gs://").partition("/")
    columns = read_gcs_header(bucket_name, blob_name)
    schema = [bigquery.SchemaField(name, "STRING") for name in columns]

    table_id = f"{project}.{dataset}.{table}"
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        schema=schema,
        skip_leading_rows=1,
        allow_quoted_newlines=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        max_bad_records=max_bad_records,
    )
    print(f"Loading {gcs_uri} -> {table_id} ({len(columns)} cols, all STRING) ...")
    job = client.load_table_from_uri(gcs_uri, table_id, job_config=job_config)
    job.result()
    dest = client.get_table(table_id)
    skipped = len(job.errors) if job.errors else 0
    print(f"Loaded {dest.num_rows:,} rows into {table_id} (skipped {skipped} bad rows).")


def main() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass  # env vars can also be exported directly (e.g. in Cloud Shell)

    competition = env("KAGGLE_COMPETITION", "santander-product-recommendation")
    file_name = env("KAGGLE_FILE", "train_ver2.csv")
    project = env("GCP_PROJECT")
    bucket = env("GCS_BUCKET")
    bq_dataset = env("BQ_DATASET", "raw")
    bq_table = env("BQ_RAW_TABLE", "santander_customer_month")
    bq_location = env("BQ_LOCATION", "US")
    max_bad_records = int(env("BQ_MAX_BAD_RECORDS", "100"))

    blob_name = f"santander/{file_name}"
    client = storage.Client()
    blob = client.bucket(bucket).blob(blob_name)

    if blob.exists():
        gcs_uri = f"gs://{bucket}/{blob_name}"
        print(f"{gcs_uri} already present — skipping Kaggle download.")
    else:
        data_dir = Path(os.environ.get("DATA_DIR", "data"))
        csv_path = download_from_kaggle_competition(competition, file_name, data_dir)
        gcs_uri = upload_to_gcs(csv_path, bucket, blob_name)

    load_into_bigquery(gcs_uri, project, bq_dataset, bq_table, bq_location, max_bad_records)
    print("Done.")


if __name__ == "__main__":
    main()
