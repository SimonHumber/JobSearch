from __future__ import annotations

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.groq_summarize import summarize_job_descriptions
from app.normalize import normalize_job
from app.schemas import (
    JobOut,
    JobsSearchResponse,
    SummarizeJobsRequest,
    SummarizeJobsResponse,
)

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
    num_pages: int = Query(1, ge=1, le=50, alias="numPages"),
) -> JobsSearchResponse:
    settings = get_settings()
    if not settings.rapid_api_key.strip():
        raise HTTPException(
            status_code=503,
            detail="RAPID_API_KEY is not configured on the server.",
        )

    query = _build_query(job_title, location)
    if not query:
        return JobsSearchResponse(jobs=[])

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

    return JobsSearchResponse(jobs=jobs)


_MAX_SUMMARIZE_JOBS = 300


@app.post("/api/jobs/summarize-descriptions", response_model=SummarizeJobsResponse)
async def summarize_job_postings(body: SummarizeJobsRequest) -> SummarizeJobsResponse:
    settings = get_settings()
    key = settings.groq_api_key.strip()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY is not configured on the server.",
        )
    if len(body.jobs) > _MAX_SUMMARIZE_JOBS:
        raise HTTPException(
            status_code=400,
            detail=f"At most {_MAX_SUMMARIZE_JOBS} jobs per request (got {len(body.jobs)}).",
        )
    summaries = await summarize_job_descriptions(
        body.jobs,
        api_key=key,
        model=settings.groq_model.strip(),
    )
    return SummarizeJobsResponse(summaries=summaries)
