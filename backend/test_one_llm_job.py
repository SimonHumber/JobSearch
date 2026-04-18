from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.config import get_settings
from app.schemas import JobDescriptionIn
from app.groq_summarize import summarize_job_descriptions

DEFAULT_ID = "test-job-1"
DEFAULT_DESCRIPTION = (
    "Software Engineer role in Toronto. Build backend APIs with Python and FastAPI, "
    "work with React frontend teams, and ship production features."
)
DEFAULT_FIRST_JOB_FILE = "first_job_posting.json"


def _load_first_job_description(path: Path) -> tuple[str, str | None] | None:
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list) or not jobs:
        return None
    first = jobs[0]
    if not isinstance(first, dict):
        return None
    description = str(first.get("description") or "").strip()
    company = str(first.get("company") or "").strip() or None
    if not description:
        return None
    return description, company


def _load_cached_first_job_description(path: Path) -> tuple[str, str | None] | None:
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        return None
    first = data.get("job")
    if not isinstance(first, dict):
        return None
    description = str(first.get("description") or "").strip()
    company = str(first.get("company") or "").strip() or None
    if not description:
        return None
    return description, company


async def _run(description: str, company: str | None = None) -> None:
    settings = get_settings()
    key = settings.groq_api_key.strip()
    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured.")

    company_text = (company or "").strip()
    user_description = (
        f"Company: {company_text}\n\nJob description:\n{description}"
        if company_text
        else description
    )

    summaries = await summarize_job_descriptions(
        [JobDescriptionIn(id=DEFAULT_ID, description=user_description)],
        api_key=key,
        model=settings.groq_model.strip(),
    )
    if not summaries:
        print("No summary returned.")
        return
    print(json.dumps(summaries[0].model_dump(), ensure_ascii=True, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run LLM summarization on one job posting."
    )
    parser.add_argument("--description", help="Job description text to summarize")
    parser.add_argument(
        "--from-jobs-json",
        action="store_true",
        help="Use the first job description from ../frontend/public/jobs.json",
    )
    parser.add_argument(
        "--from-first-job-file",
        action="store_true",
        help=f"Use first posting from ./{DEFAULT_FIRST_JOB_FILE}",
    )
    parser.add_argument(
        "--first-job-file",
        default=DEFAULT_FIRST_JOB_FILE,
        help="Path to cached first-job posting JSON file",
    )
    args = parser.parse_args()

    description = (args.description or "").strip()
    company: str | None = None

    if args.from_jobs_json:
        jobs_json = (
            Path(__file__).resolve().parent / "../frontend/public/jobs.json"
        ).resolve()
        loaded = _load_first_job_description(jobs_json)
        if loaded:
            description, company = loaded
        else:
            print(
                f"Could not load first job from {jobs_json}; falling back to defaults."
            )

    cached_file = Path(args.first_job_file)
    if not cached_file.is_absolute():
        cached_file = (Path(__file__).resolve().parent / cached_file).resolve()

    should_try_cached = args.from_first_job_file or (
        not description and not args.from_jobs_json
    )
    if should_try_cached:
        loaded = _load_cached_first_job_description(cached_file)
        if loaded:
            description, company = loaded
        else:
            print(
                f"Could not load first job from {cached_file}; falling back to defaults."
            )

    if not description:
        description = DEFAULT_DESCRIPTION

    asyncio.run(_run(description, company=company))


if __name__ == "__main__":
    main()
