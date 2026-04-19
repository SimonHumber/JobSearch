from __future__ import annotations

import json
from typing import Any

import psycopg


def init_db(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS companies (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    address TEXT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS job_postings (
                    id TEXT PRIMARY KEY,
                    company_id BIGINT NULL REFERENCES companies(id) ON DELETE SET NULL,
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        conn.commit()


def replace_job_postings(
    database_url: str,
    jobs: list[dict[str, Any]],
) -> None:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE job_postings;")
            for job in jobs:
                company_name = str(job.get("company") or "").strip()
                company_id: int | None = None
                if company_name:
                    cur.execute(
                        """
                        INSERT INTO companies (name, address)
                        VALUES (%s, NULL)
                        ON CONFLICT (name) DO NOTHING
                        RETURNING id;
                        """,
                        (company_name,),
                    )
                    row = cur.fetchone()
                    if row:
                        company_id = int(row[0])
                    else:
                        cur.execute(
                            "SELECT id FROM companies WHERE name = %s;",
                            (company_name,),
                        )
                        existing = cur.fetchone()
                        if existing:
                            company_id = int(existing[0])

                job_id = str(job.get("id") or "").strip()
                if not job_id:
                    continue
                cur.execute(
                    """
                    INSERT INTO job_postings (id, company_id, payload)
                    VALUES (%s, %s, %s::jsonb);
                    """,
                    (job_id, company_id, json.dumps(job, ensure_ascii=False)),
                )
        conn.commit()


def load_job_feed(database_url: str) -> dict[str, Any]:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload, created_at
                FROM job_postings
                ORDER BY created_at DESC, id ASC;
                """
            )
            rows = cur.fetchall()

    jobs: list[dict[str, Any]] = []
    generated_at: str | None = None
    for idx, row in enumerate(rows):
        payload = row[0]
        created_at = row[1]
        if idx == 0 and created_at is not None:
            generated_at = str(created_at.isoformat())
        if isinstance(payload, dict):
            jobs.append(payload)
    return {"generatedAt": generated_at, "jobs": jobs}
