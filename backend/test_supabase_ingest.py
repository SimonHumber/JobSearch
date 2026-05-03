from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import psycopg

from app.config import get_settings
from app.db import init_db, replace_job_postings


def _load_jobs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        jobs = data.get("jobs")
        if isinstance(jobs, list):
            return [j for j in jobs if isinstance(j, dict)]
    if isinstance(data, list):
        return [j for j in data if isinstance(j, dict)]
    raise ValueError("Expected JSON object with 'jobs' array or a top-level array.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test ingestion of job postings into Supabase Postgres."
    )
    parser.add_argument(
        "--input",
        default="../frontend/public/jobs.json",
        help="Path to input JSON file (default: ../frontend/public/jobs.json)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional number of jobs to ingest for testing (0 = all)",
    )
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = (base / input_path).resolve()

    settings = get_settings()
    db_url = settings.postgres_url
    if not db_url:
        raise RuntimeError("Set SUPABASE_URL (or DATABASE_URL) in backend/.env.")

    jobs = _load_jobs(input_path)
    if args.limit and args.limit > 0:
        jobs = jobs[: args.limit]
    if not jobs:
        raise RuntimeError("No jobs found to ingest.")

    print(f"[test] Input file: {input_path}")
    print(f"[test] Jobs to ingest: {len(jobs)}")

    print("[test] Ensuring schema exists")
    init_db(db_url)

    print("[test] Replacing job_postings with test payload")
    replace_job_postings(db_url, jobs)

    with psycopg.connect(db_url, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM job_postings;")
            postings_count = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM companies;")
            companies_count = int(cur.fetchone()[0])

    print(f"[ok] job_postings rows: {postings_count}")
    print(f"[ok] companies rows: {companies_count}")


if __name__ == "__main__":
    main()
