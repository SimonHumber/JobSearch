"""Batch job-description summaries via Groq (OpenAI-compatible chat API)."""

from __future__ import annotations

import asyncio

from groq import Groq

from app.schemas import JobDescriptionIn, JobSummaryOut

_MAX_DESC_CHARS = 24_000
_CONCURRENCY = 6

_SYSTEM = (
    "Write a concicse summary of the description. Only mention what is in the description. Only give summary"
    "Lead with salary if it is explicitly given in the description. Very first sentence should be the salary."
    "Then, give max 5 sentence summary of job responsibilities, then list qualifications in bullet points."
    "Give in plain text. Do no give markdown"
)


def _summarize_one(
    job_id: str,
    description: str,
    *,
    client: Groq,
    model: str,
) -> JobSummaryOut:
    text = (description or "").strip()
    if not text or text == "No description provided.":
        return JobSummaryOut(id=job_id, summary="", error=None)

    truncated = text[:_MAX_DESC_CHARS]
    user_msg = (
        "Summarize this entire job description. Include responsibilities, requirements, "
        "qualifications, and benefits or work arrangement if stated. Do not invent details.\n\n"
        + truncated
    )
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=700,
        )
        choice = completion.choices[0].message
        content = (choice.content or "").strip()
        return JobSummaryOut(id=job_id, summary=content, error=None)
    except Exception as e:
        return JobSummaryOut(id=job_id, summary="", error=str(e)[:500])


async def summarize_job_descriptions(
    jobs: list[JobDescriptionIn],
    *,
    api_key: str,
    model: str,
) -> list[JobSummaryOut]:
    if not jobs:
        return []

    client = Groq(api_key=api_key)
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def run(j: JobDescriptionIn) -> JobSummaryOut:
        async with sem:
            return await asyncio.to_thread(
                _summarize_one,
                j.id,
                j.description,
                client=client,
                model=model,
            )

    return list(await asyncio.gather(*[run(j) for j in jobs]))
