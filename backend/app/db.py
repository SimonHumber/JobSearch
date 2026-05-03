from __future__ import annotations

import json
from typing import Any

import httpx
import psycopg

# psycopg3 prepares statements by default; Supabase PgBouncer (transaction
# pooling) can reuse backends and raise DuplicatePreparedStatement.
_PG_CONN_KWARGS: dict[str, Any] = {"prepare_threshold": None}


def init_db(database_url: str) -> None:
    with psycopg.connect(database_url, **_PG_CONN_KWARGS) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS companies (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    address TEXT NULL,
                    lat DOUBLE PRECISION NULL,
                    long DOUBLE PRECISION NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                ALTER TABLE companies
                ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION NULL;
                """
            )
            cur.execute(
                """
                ALTER TABLE companies
                ADD COLUMN IF NOT EXISTS long DOUBLE PRECISION NULL;
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


def load_known_company_addresses(database_url: str) -> dict[str, str]:
    """Return a {company_name: address} map for companies with a known address."""
    out: dict[str, str] = {}
    with psycopg.connect(database_url, **_PG_CONN_KWARGS) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT name, address
                FROM companies
                WHERE address IS NOT NULL AND btrim(address) <> '';
                """
            )
            for row in cur.fetchall():
                name = str(row[0] or "").strip()
                address = str(row[1] or "").strip()
                if name and address:
                    out[name] = address
    return out


def replace_job_postings(
    database_url: str,
    jobs: list[dict[str, Any]],
) -> None:
    with psycopg.connect(database_url, **_PG_CONN_KWARGS) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE job_postings;")
            for job in jobs:
                company_name = str(job.get("company") or "").strip()
                company_id: int | None = None
                if company_name:
                    company_address = str(
                        job.get("aiOfficeLocationToronto")
                        or job.get("office_location_toronto")
                        or ""
                    ).strip() or None
                    cur.execute(
                        """
                        INSERT INTO companies (name, address)
                        VALUES (%s, %s)
                        ON CONFLICT (name) DO UPDATE
                        SET address = COALESCE(EXCLUDED.address, companies.address)
                        RETURNING id;
                        """,
                        (company_name, company_address),
                    )
                    row = cur.fetchone()
                    if row:
                        company_id = int(row[0])

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


def geocode_companies_missing_coords(
    database_url: str,
    *,
    map_api_key: str,
) -> None:
    key = (map_api_key or "").strip()
    if not key:
        print("[geo] MAP_API_KEY missing; skipping geocoding")
        return

    with psycopg.connect(database_url, **_PG_CONN_KWARGS) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, address
                FROM companies
                WHERE address IS NOT NULL
                  AND btrim(address) <> ''
                  AND (lat IS NULL OR long IS NULL)
                ORDER BY id ASC;
                """
            )
            rows = cur.fetchall()

            if not rows:
                print("[geo] No companies with missing coordinates")
                return

            print(f"[geo] Geocoding {len(rows)} companies")
            client = httpx.Client(timeout=20.0)
            updated = 0
            try:
                for row in rows:
                    company_id = int(row[0])
                    company_name = str(row[1] or "").strip()
                    address = str(row[2] or "").strip()
                    if not address:
                        continue

                    geo_who = f"{company_name}: " if company_name else ""

                    response = client.get(
                        "https://maps.googleapis.com/maps/api/geocode/json",
                        params={"address": address, "key": key},
                    )
                    if response.status_code != 200:
                        print(
                            f"[geo] {geo_who}HTTP {response.status_code}; skipping"
                        )
                        continue

                    payload = response.json()
                    status = str(payload.get("status") or "")
                    if status != "OK":
                        print(
                            f"[geo] {geo_who}geocode status={status}; skipping"
                        )
                        continue

                    results = payload.get("results")
                    if not isinstance(results, list) or not results:
                        print(
                            f"[geo] {geo_who}no geocode results; skipping"
                        )
                        continue

                    first = results[0]
                    if not isinstance(first, dict):
                        continue
                    geometry = first.get("geometry")
                    if not isinstance(geometry, dict):
                        continue
                    location = geometry.get("location")
                    if not isinstance(location, dict):
                        continue

                    lat = location.get("lat")
                    lng = location.get("lng")
                    if not isinstance(lat, (int, float)) or not isinstance(
                        lng, (int, float)
                    ):
                        print(
                            f"[geo] {geo_who}invalid lat/lng; skipping"
                        )
                        continue

                    cur.execute(
                        """
                        UPDATE companies
                        SET lat = %s, long = %s
                        WHERE id = %s;
                        """,
                        (float(lat), float(lng), company_id),
                    )
                    updated += 1
            finally:
                client.close()

        conn.commit()
    print(f"[geo] Updated coordinates for {updated} companies")


def load_job_feed(database_url: str) -> dict[str, Any]:
    with psycopg.connect(database_url, **_PG_CONN_KWARGS) as conn:
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
