from __future__ import annotations

import argparse
import asyncio
import hashlib
from typing import Any

import httpx

from app.config import get_settings
from app.db import (
    geocode_companies_missing_coords,
    init_db,
    load_known_company_addresses,
    replace_job_postings,
)
from app.groq_summarize import summarize_job_descriptions
from app.schemas import JobDescriptionIn, JobOut

DEFAULT_QUERY_JOB_TITLES: list[str] = [
    "software engineer",
    "software developer",
    "frontend developer",
    "backend developer",
    "full stack developer",
    "mobile developer",
    "ios developer",
    "android developer",
    "devops",
    "site reliability engineer",
    "data engineer",
    "mlops",
    "machine learning engineer",
]

DEFAULT_QUERY_LOCATION = "Toronto"
DEFAULT_TOTAL_PAGE_BUDGET = 25
DEFAULT_SEARCH_RADIUS_KM = 25
DEFAULT_DATE_POSTED = "week"  # any, 3days, week, month

_DATE_POSTED_CHIPS: dict[str, str] = {
    "today": "date_posted:today",
    "3days": "date_posted:3days",
    "week": "date_posted:week",
    "month": "date_posted:month",
    "any": "",
}


def _build_query(job_title: str, location: str) -> str:
    title = job_title.strip()
    if title:
        return title
    return location.strip()


def _split_location(location: str) -> tuple[str | None, str | None, str | None]:
    parts = [p.strip() for p in location.split(",") if p and p.strip()]
    city = parts[0] if len(parts) >= 1 else None
    state = parts[1] if len(parts) >= 2 else None
    country = parts[2] if len(parts) >= 3 else None
    return city, state, country


def _extract_serp_description(item: dict[str, Any]) -> str:
    desc = str(item.get("description") or "").strip()
    if desc:
        return desc

    highlights = item.get("job_highlights")
    if not isinstance(highlights, list):
        return "No description provided."

    lines: list[str] = []
    for section in highlights:
        if not isinstance(section, dict):
            continue
        title = str(section.get("title") or "").strip()
        items = section.get("items")
        if title:
            lines.append(f"{title}:")
        if isinstance(items, list):
            for bullet in items:
                b = str(bullet or "").strip()
                if b:
                    lines.append(f"- {b}")
    return "\n".join(lines).strip() or "No description provided."


def _extract_serp_salary_display(item: dict[str, Any]) -> str | None:
    detected = item.get("detected_extensions")
    if isinstance(detected, dict):
        salary = str(detected.get("salary") or "").strip()
        if salary:
            return salary
    extensions = item.get("extensions")
    if isinstance(extensions, list):
        for ext in extensions:
            text = str(ext or "").strip()
            if "$" in text:
                return text
    return None


def _extract_serp_posted_display(item: dict[str, Any]) -> str | None:
    detected = item.get("detected_extensions")
    if isinstance(detected, dict):
        posted = str(detected.get("posted_at") or "").strip()
        if posted:
            return posted
    return None


def _extract_serp_apply_options(item: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(publisher: str, link: str) -> None:
        href = str(link or "").strip()
        if not href or href in seen:
            return
        seen.add(href)
        pub = str(publisher or "").strip() or "Apply"
        out.append({"publisher": pub, "applyLink": href})

    raw_apply = item.get("apply_options")
    if isinstance(raw_apply, list):
        for option in raw_apply:
            if not isinstance(option, dict):
                continue
            add(
                str(option.get("title") or option.get("publisher") or "Apply"),
                str(option.get("link") or option.get("apply_link") or ""),
            )

    raw_related = item.get("related_links")
    if isinstance(raw_related, list):
        for option in raw_related:
            if not isinstance(option, dict):
                continue
            add(
                str(option.get("text") or option.get("title") or "Apply"),
                str(option.get("link") or ""),
            )

    return out


def _serp_item_to_job_dict(item: dict[str, Any]) -> dict[str, Any]:
    title = str(item.get("title") or "").strip() or "Untitled role"
    company = str(item.get("company_name") or item.get("company") or "").strip()
    location = str(item.get("location") or "").strip() or "Location not listed"
    city, state, country = _split_location(location)
    description = _extract_serp_description(item)
    salary_display = _extract_serp_salary_display(item)
    posted_display = _extract_serp_posted_display(item)
    publisher = str(item.get("via") or "").strip() or None

    raw_id = str(item.get("job_id") or "").strip()
    if raw_id:
        job_id = raw_id
    else:
        # Hash only stable posting fields so the same listing surfaced by
        # different queries still collapses to one id.
        stable = f"{title}|{company}|{location}|{description}"
        job_id = "serp-" + hashlib.sha1(stable.encode("utf-8")).hexdigest()[:16]

    return {
        "id": job_id,
        "title": title,
        "company": company or "Company not listed",
        "location": location,
        "postedAt": None,
        "postedDisplay": posted_display,
        "description": description,
        "salaryDisplay": salary_display,
        "listingSource": publisher,
        "jobPublisher": publisher,
        "jobMinSalary": None,
        "jobMaxSalary": None,
        "jobMedianSalary": None,
        "jobSalaryCurrency": None,
        "jobSalaryPeriod": None,
        "jobCity": city,
        "jobState": state,
        "jobCountry": country,
        "jobLocation": location,
        "employerName": company or None,
        "applyOptions": _extract_serp_apply_options(item),
    }


async def _fetch_jobs(
    *,
    job_titles: list[str],
    location: str,
    total_page_budget: int,
    date_posted: str,
) -> list[dict[str, Any]]:
    titles = [t.strip() for t in job_titles if t and t.strip()]
    if not titles:
        return []

    chip_value = _DATE_POSTED_CHIPS.get(
        date_posted, _DATE_POSTED_CHIPS[DEFAULT_DATE_POSTED]
    )
    print(
        f"[fetch] Querying SerpApi Google Jobs in '{location}' across "
        f"{len(titles)} query/queries "
        f"(total_page_budget={total_page_budget}, date_posted={date_posted})"
    )
    settings = get_settings()
    key = settings.serpapi_key.strip()
    if not key:
        raise RuntimeError("SERPAPI_KEY is required.")

    url = settings.serpapi_base.rstrip("/")
    jobs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    pages_used = 0

    async with httpx.AsyncClient(timeout=120.0) as client:
        for query_idx, title in enumerate(titles, start=1):
            if pages_used >= total_page_budget:
                print(
                    f"[fetch] Page budget ({total_page_budget}) exhausted; "
                    f"stopping before query {query_idx}/{len(titles)}."
                )
                break

            query = _build_query(title, location)
            if not query:
                continue

            remaining = total_page_budget - pages_used
            print(
                f"[fetch] Query {query_idx}/{len(titles)}: {query!r} "
                f"(pages remaining in budget: {remaining})"
            )

            next_page_token: str | None = None
            query_pages = 0
            for page_offset in range(remaining):
                pages_used += 1
                query_pages += 1
                request_label = f"query={query_idx} page={page_offset + 1}"
                params: dict[str, Any] = {
                    "engine": "google_jobs",
                    "q": query,
                    "api_key": key,
                    "hl": "en",
                    "location": location,
                    "lrad": DEFAULT_SEARCH_RADIUS_KM,
                }
                if chip_value:
                    params["chips"] = chip_value
                if next_page_token:
                    params["next_page_token"] = next_page_token

                response = await client.get(url, params=params)
                if response.status_code != 200:
                    raise RuntimeError(
                        f"SerpApi error ({response.status_code}) at {request_label}: "
                        f"{response.text[:500]}"
                    )

                payload = response.json()
                page_jobs = (
                    payload.get("jobs_results") if isinstance(payload, dict) else None
                )
                if not isinstance(page_jobs, list):
                    page_jobs = []

                print(f"[fetch] {request_label} returned {len(page_jobs)} jobs")
                if not page_jobs:
                    print(
                        f"[fetch] Empty page for query {query_idx}; "
                        "moving to next query."
                    )
                    break

                for item in page_jobs:
                    if not isinstance(item, dict):
                        continue
                    job = _serp_item_to_job_dict(item)
                    job_id = str(job.get("id") or "").strip()
                    if job_id and job_id in seen_ids:
                        continue
                    if job_id:
                        seen_ids.add(job_id)
                    jobs.append(JobOut.model_validate(job).model_dump())

                pagination = (
                    payload.get("serpapi_pagination")
                    if isinstance(payload, dict)
                    else None
                )
                token_value = (
                    pagination.get("next_page_token")
                    if isinstance(pagination, dict)
                    else None
                )
                next_page_token = str(token_value).strip() if token_value else None
                if not next_page_token:
                    print(
                        f"[fetch] No next_page_token for query {query_idx}; "
                        "moving to next query."
                    )
                    break

            print(
                f"[fetch] Query {query_idx} consumed {query_pages} page(s); "
                f"total used: {pages_used}/{total_page_budget}"
            )

    print(
        f"[fetch] Retrieved {len(jobs)} unique jobs across "
        f"{pages_used} page(s)"
    )
    return jobs


def _merge_summaries(
    jobs: list[dict[str, Any]], summaries: list[dict[str, Any]]
) -> None:
    by_id = {str(s.get("id")): s for s in summaries}
    for job in jobs:
        prefilled = bool(job.get("_prefilled_office_location"))
        prefilled_address = (
            str(job.get("aiOfficeLocationToronto") or "").strip() if prefilled else ""
        )

        sid = str(job.get("id"))
        s = by_id.get(sid)
        if not s:
            job["aiSummary"] = None
            if prefilled and prefilled_address:
                job["aiOfficeLocationToronto"] = prefilled_address
            else:
                job["aiOfficeLocationToronto"] = None
            job["aiSummaryError"] = "No summary returned for this job."
            job.pop("_prefilled_office_location", None)
            continue

        desc = (s.get("description") or "").strip()
        salary = (s.get("salary") or "").strip()
        office = (s.get("office_location_toronto") or "").strip()
        err = (s.get("error") or "").strip()

        if salary and not str(job.get("salaryDisplay") or "").strip():
            job["salaryDisplay"] = salary
        job["aiSummary"] = desc or None
        if prefilled and prefilled_address:
            job["aiOfficeLocationToronto"] = prefilled_address
        else:
            job["aiOfficeLocationToronto"] = office or None
        job["aiSummaryError"] = err or None
        job.pop("_prefilled_office_location", None)


async def generate_jobs_json(
    *,
    job_titles: list[str],
    location: str,
    total_page_budget: int,
    date_posted: str,
) -> None:
    print("[run] Starting jobs feed generation")
    jobs = await _fetch_jobs(
        job_titles=job_titles,
        location=location,
        total_page_budget=total_page_budget,
        date_posted=date_posted,
    )

    settings = get_settings()

    db_url = settings.postgres_url
    if not db_url:
        raise RuntimeError("Set SUPABASE_URL (or DATABASE_URL) in backend/.env.")
    print("[db] Initializing database schema")
    init_db(db_url)

    known_addresses: dict[str, str] = {}
    if jobs:
        known_addresses = load_known_company_addresses(db_url)
        print(f"[db] Loaded {len(known_addresses)} known company addresses")
        prefilled_count = 0
        for job in jobs:
            company_name = str(job.get("company") or "").strip()
            if not company_name:
                continue
            known = known_addresses.get(company_name)
            if known:
                job["aiOfficeLocationToronto"] = known
                job["_prefilled_office_location"] = True
                prefilled_count += 1
        if prefilled_count:
            print(
                f"[db] Pre-filled office address for {prefilled_count} job(s) from companies table"
            )

    gemini_key = settings.google_api_key.strip()
    if gemini_key and jobs:
        print(
            f"[llm] Running summaries for {len(jobs)} jobs with model '{settings.gemini_model.strip()}'"
        )
        summaries = await summarize_job_descriptions(
            [
                JobDescriptionIn(
                    id=str(j["id"]),
                    description=str(j["description"]),
                    company=str(j.get("company") or "").strip() or None,
                )
                for j in jobs
            ],
            api_key=gemini_key,
            model=settings.gemini_model.strip(),
        )
        _merge_summaries(jobs, [s.model_dump() for s in summaries])
        print("[llm] Summary merge complete")
    elif not gemini_key:
        print("[llm] GOOGLE_API_KEY missing; skipping summaries")
    else:
        print("[llm] No jobs returned; skipping summaries")

    print("[db] Replacing job_postings contents")
    replace_job_postings(db_url, jobs)
    print("[geo] Geocoding companies with known address but missing coordinates")
    geocode_companies_missing_coords(
        db_url,
        map_api_key=settings.map_api_key,
    )
    print(f"[done] Ingested {len(jobs)} jobs to database")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch jobs and ingest into database.")
    parser.add_argument(
        "--job-title",
        nargs="+",
        default=DEFAULT_QUERY_JOB_TITLES,
        help=(
            "One or more job title queries, tried in order. When a query "
            "returns an empty page, the next query consumes the remaining "
            "page budget."
        ),
    )
    parser.add_argument("--location", default=DEFAULT_QUERY_LOCATION)
    parser.add_argument(
        "--total-page-budget",
        type=int,
        default=DEFAULT_TOTAL_PAGE_BUDGET,
        help="Total SerpApi page calls shared across all queries.",
    )
    parser.add_argument(
        "--date-posted",
        choices=sorted(_DATE_POSTED_CHIPS.keys()),
        default=DEFAULT_DATE_POSTED,
        help="Filter by posting date.",
    )
    args = parser.parse_args()

    job_titles = (
        list(args.job_title)
        if isinstance(args.job_title, list)
        else [args.job_title]
    )

    asyncio.run(
        generate_jobs_json(
            job_titles=job_titles,
            location=args.location,
            total_page_budget=max(1, min(100, args.total_page_budget)),
            date_posted=args.date_posted,
        )
    )
    print("Database ingest complete.")


if __name__ == "__main__":
    main()
