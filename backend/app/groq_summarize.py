"""Batch job-description summaries via Groq (JSON: description + salary)."""

from __future__ import annotations

import asyncio
import json
import re

from groq import Groq

from app.schemas import JobDescriptionIn, JobSummaryOut

_MAX_DESC_CHARS = 24_000
_CONCURRENCY = 6

# JSON envelope + your original description rules (description + salary keys).
_SYSTEM = (
    "Return a valid JSON object with exactly two keys: 'description' and 'salary'. "
    "Keep the output strictly JSON; no preamble or conversational filler."
    "\n\n"
    "1. 'salary':\n"
    "- Extract the exact salary text ONLY if it contains digits (0-9).\n"
    "- If no digits are present, output null.\n"
    "- This is a strict rule: output MUST be either:\n"
    "  (a) a string containing digits, or\n"
    "  (b) null\n"
    "- No other text is allowed.\n"
    "\n"
    "2. For 'description': Provide a single string containing a summary of the role "
    "followed by a list of qualifications. Use standard dashes (-) for bullets and "
    "newline characters (\\n) for spacing. Avoid all Markdown formatting like bolding (**) or headers (#)."
)


def _strip_json_fence(content: str) -> str:
    raw = content.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, count=1, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```\s*$", "", raw, count=1)
    return raw.strip()


def _parse_llm_json(content: str) -> tuple[str, str | None]:
    raw = _strip_json_fence(content)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    desc = data.get("description")
    description = str(desc).strip() if desc is not None else ""
    sal = data.get("salary")
    if sal is None or (isinstance(sal, str) and not sal.strip()):
        salary: str | None = None
    else:
        salary = str(sal).strip() or None
    return description, salary


def _summarize_one(
    job_id: str,
    description_text: str,
    *,
    client: Groq,
    model: str,
) -> JobSummaryOut:
    text = (description_text or "").strip()
    if not text or text == "No description provided.":
        return JobSummaryOut(id=job_id, description="", salary=None, error=None)

    truncated = text[:_MAX_DESC_CHARS]
    # User message is only the posting text; instructions live in the system prompt.
    user_msg = truncated
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=900,
            response_format={"type": "json_object"},
        )
        choice = completion.choices[0].message
        content = (choice.content or "").strip()
        description, salary = _parse_llm_json(content)
        return JobSummaryOut(
            id=job_id, description=description, salary=salary, error=None
        )
    except Exception as e:
        return JobSummaryOut(
            id=job_id,
            description="",
            salary=None,
            error=str(e)[:500],
        )


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
