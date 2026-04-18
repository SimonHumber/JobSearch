from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings
from app.groq_summarize import summarize_job_descriptions
from app.normalize import normalize_job
from app.schemas import JobDescriptionIn, JobOut

DEFAULT_OUTPUT_PATH = "../frontend/public/jobs.json"
DEFAULT_QUERY_JOB_TITLE = "software engineer"
DEFAULT_QUERY_LOCATION = "Toronto"
DEFAULT_QUERY_PAGE = 1
DEFAULT_QUERY_NUM_PAGES = 1


def _build_query(job_title: str, location: str) -> str:
    title = job_title.strip()
    loc = location.strip()
    if title and loc:
        return f"{title} in {loc}"
    return title or loc


async def _fetch_jobs(
    *,
    job_title: str,
    location: str,
    page: int,
    num_pages: int,
) -> list[dict[str, Any]]:
    print(
        f"[fetch] Querying JSearch for '{job_title}' in '{location}' "
        f"(page={page}, num_pages={num_pages})"
    )
    settings = get_settings()
    key = settings.rapid_api_key.strip()
    if not key:
        raise RuntimeError("RAPID_API_KEY is required.")

    query = _build_query(job_title, location)
    params = {"query": query, "page": page, "num_pages": num_pages}
    headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": settings.jsearch_host}
    url = f"{settings.jsearch_base.rstrip('/')}/search"

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.get(url, params=params, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(
            f"JSearch error ({response.status_code}): {response.text[:500]}"
        )

    payload = response.json()
    raw_jobs = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_jobs, list):
        raw_jobs = []

    jobs: list[dict[str, Any]] = []
    for i, item in enumerate(raw_jobs):
        if not isinstance(item, dict):
            continue
        normalized = normalize_job(item, i)
        jobs.append(JobOut.model_validate(normalized).model_dump())
    print(f"[fetch] Retrieved {len(jobs)} jobs")
    return jobs


def _merge_summaries(
    jobs: list[dict[str, Any]], summaries: list[dict[str, Any]]
) -> None:
    by_id = {str(s.get("id")): s for s in summaries}
    for job in jobs:
        sid = str(job.get("id"))
        s = by_id.get(sid)
        if not s:
            job["aiSummary"] = None
            job["aiOfficeLocationToronto"] = None
            job["aiSummaryError"] = "No summary returned for this job."
            continue

        desc = (s.get("description") or "").strip()
        salary = (s.get("salary") or "").strip()
        office = (s.get("office_location_toronto") or "").strip()
        err = (s.get("error") or "").strip()

        if salary and not str(job.get("salaryDisplay") or "").strip():
            job["salaryDisplay"] = salary
        job["aiSummary"] = desc or None
        job["aiOfficeLocationToronto"] = office or None
        job["aiSummaryError"] = err or None


async def generate_jobs_json(
    *,
    output: Path,
    job_title: str,
    location: str,
    page: int,
    num_pages: int,
) -> None:
    print("[run] Starting jobs feed generation")
    jobs = await _fetch_jobs(
        job_title=job_title,
        location=location,
        page=page,
        num_pages=num_pages,
    )

    settings = get_settings()
    groq_key = settings.groq_api_key.strip()
    if groq_key and jobs:
        print(
            f"[llm] Running summaries for {len(jobs)} jobs with model '{settings.groq_model.strip()}'"
        )
        summaries = await summarize_job_descriptions(
            [
                JobDescriptionIn(
                    id=str(j["id"]),
                    description=(
                        f"Company: {str(j.get('company') or '').strip()}\n\n"
                        f"Job description:\n{str(j['description'])}"
                        if str(j.get("company") or "").strip()
                        else str(j["description"])
                    ),
                )
                for j in jobs
            ],
            api_key=groq_key,
            model=settings.groq_model.strip(),
        )
        _merge_summaries(jobs, [s.model_dump() for s in summaries])
        print("[llm] Summary merge complete")
    elif not groq_key:
        print("[llm] GROQ_API_KEY missing; skipping summaries")
    else:
        print("[llm] No jobs returned; skipping summaries")

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "query": job_title,
        "location": location,
        "numPages": num_pages,
        "jobs": jobs,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"[write] Writing output to {output}")
    output.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    print(f"[done] Wrote {len(jobs)} jobs to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate frontend jobs.json feed.")
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument("--job-title", default=DEFAULT_QUERY_JOB_TITLE)
    parser.add_argument("--location", default=DEFAULT_QUERY_LOCATION)
    parser.add_argument("--page", type=int, default=DEFAULT_QUERY_PAGE)
    parser.add_argument("--num-pages", type=int, default=DEFAULT_QUERY_NUM_PAGES)
    args = parser.parse_args()

    out = Path(args.output)
    if not out.is_absolute():
        out = (Path(__file__).resolve().parent / out).resolve()

    asyncio.run(
        generate_jobs_json(
            output=out,
            job_title=args.job_title,
            location=args.location,
            page=max(1, args.page),
            num_pages=max(1, min(50, args.num_pages)),
        )
    )
    print(f"Wrote curated jobs feed to {out}")


if __name__ == "__main__":
    main()
