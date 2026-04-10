from __future__ import annotations

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.normalize import (
    extract_apply_options,
    normalize_job,
    raw_job_from_jsearch_detail_payload,
)
from app.schemas import ApplyOptionOut, ApplyOptionsResponse, JobOut, JobsSearchResponse

_settings = get_settings()
_cors_origins = [o.strip() for o in _settings.cors_origins.split(",") if o.strip()]

app = FastAPI(title="Job Search API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_query(job_title: str, location: str) -> str:
    title = job_title.strip()
    loc = location.strip()
    if title and loc:
        return f"{title} in {loc}"
    return title or loc


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/jobs/search", response_model=JobsSearchResponse)
async def search_jobs(
    job_title: str = Query("", alias="jobTitle"),
    location: str = Query(""),
    page: int = Query(1, ge=1),
    num_pages: int = Query(50, ge=1, le=50, alias="numPages"),
) -> JobsSearchResponse:
    settings = get_settings()
    if not settings.rapid_api_key.strip():
        raise HTTPException(
            status_code=503,
            detail="RAPID_API_KEY is not configured on the server.",
        )

    query = _build_query(job_title, location)
    if not query:
        return JobsSearchResponse(jobs=[], count=0)

    params = {"query": query, "page": page, "num_pages": num_pages}
    headers = {
        "X-RapidAPI-Key": settings.rapid_api_key.strip(),
        "X-RapidAPI-Host": settings.jsearch_host,
    }
    url = f"{settings.jsearch_base.rstrip('/')}/search"

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(url, params=params, headers=headers)
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502, detail=f"Upstream request failed: {e!s}"
        ) from e

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text[:2000] or "JSearch error",
        )

    try:
        payload = response.json()
    except ValueError as e:
        raise HTTPException(status_code=502, detail="Invalid JSON from JSearch") from e

    raw_jobs = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_jobs, list):
        raw_jobs = []

    jobs: list[JobOut] = []
    for i, item in enumerate(raw_jobs):
        if not isinstance(item, dict):
            continue
        normalized = normalize_job(item, i)
        jobs.append(JobOut.model_validate(normalized))

    return JobsSearchResponse(jobs=jobs, count=len(jobs))


@app.get("/api/jobs/apply-options", response_model=ApplyOptionsResponse)
async def job_apply_options(
    job_id: str = Query("", alias="jobId", min_length=1),
) -> ApplyOptionsResponse:
    """Fetch apply links from JSearch job-details when search omitted them."""
    settings = get_settings()
    if not settings.rapid_api_key.strip():
        raise HTTPException(
            status_code=503,
            detail="RAPID_API_KEY is not configured on the server.",
        )

    headers = {
        "X-RapidAPI-Key": settings.rapid_api_key.strip(),
        "X-RapidAPI-Host": settings.jsearch_host,
    }
    url = f"{settings.jsearch_base.rstrip('/')}/job-details"
    params = {"job_id": job_id.strip()}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, params=params, headers=headers)
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502, detail=f"Upstream request failed: {e!s}"
        ) from e

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text[:2000] or "JSearch error",
        )

    try:
        payload = response.json()
    except ValueError as e:
        raise HTTPException(status_code=502, detail="Invalid JSON from JSearch") from e

    raw = raw_job_from_jsearch_detail_payload(payload)
    opts = extract_apply_options(raw)
    return ApplyOptionsResponse(
        applyOptions=[ApplyOptionOut.model_validate(o) for o in opts],
    )
