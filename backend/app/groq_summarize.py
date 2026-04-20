"""Batch job-description summaries via Gemini."""

from __future__ import annotations

import asyncio
import json
import time
import re

import httpx

from app.schemas import JobDescriptionIn, JobSummaryOut

_MAX_DESC_CHARS = 24_000
_LLM_CALL_INTERVAL_SECONDS = 0
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

_SYSTEM_SUMMARY_WITH_SEARCH = (
    "Return a valid JSON object with exactly three keys: "
    "'description', 'salary', and 'office_location_toronto'. "
    "Keep the output strictly JSON; no preamble or conversational filler."
    "\n\n"
    "1. 'salary':\n"
    "- Extract the exact salary text ONLY if it contains digits (0-9).\n"
    "- If no digits are present, output null.\n"
    "- No other text is allowed.\n"
    "\n"
    "2. For 'description': provide a single string containing a summary of the role "
    "followed by a list of qualifications. Use standard dashes (-) for bullets and "
    "newline characters (\\n) for spacing. Avoid all Markdown formatting like bolding (**) or headers (#)."
    "\n\n"
    "3. For 'office_location_toronto': ONLY use the provided job description text. "
    "Do NOT use outside knowledge, do NOT guess, and do NOT use web search. "
    "Return a STREET ADDRESS (street number + street name + city) ONLY if it is "
    "explicitly written in the job description. Otherwise return null."
)


def _strip_json_fence(content: str) -> str:
    raw = content.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, count=1, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```\s*$", "", raw, count=1)
    return raw.strip()


def _parse_llm_json(content: str) -> tuple[str, str | None, str | None]:
    raw = _strip_json_fence(content)
    decoder = json.JSONDecoder()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        if start == -1:
            raise
        data, _ = decoder.raw_decode(raw[start:])
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    desc = data.get("description")
    description = str(desc).strip() if desc is not None else ""
    sal = data.get("salary")
    if sal is None or (isinstance(sal, str) and not sal.strip()):
        salary: str | None = None
    else:
        salary = str(sal).strip() or None
    office = data.get("office_location_toronto")
    if office is None or (isinstance(office, str) and not office.strip()):
        office_location_toronto: str | None = None
    else:
        office_location_toronto = str(office).strip() or None
    return description, salary, office_location_toronto


def _extract_usage_counts(
    payload: dict[str, object],
) -> tuple[int | None, int | None, int | None]:
    usage = payload.get("usageMetadata")
    if not isinstance(usage, dict):
        return None, None, None
    prompt_tokens = usage.get("promptTokenCount")
    completion_tokens = usage.get("candidatesTokenCount")
    total_tokens = usage.get("totalTokenCount")
    if not isinstance(prompt_tokens, int):
        prompt_tokens = None
    if not isinstance(completion_tokens, int):
        completion_tokens = None
    if not isinstance(total_tokens, int):
        total_tokens = None
    return prompt_tokens, completion_tokens, total_tokens


def _extract_candidate_text(payload: dict[str, object]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return ""
    first = candidates[0]
    if not isinstance(first, dict):
        return ""
    content = first.get("content")
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    chunks: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if text is None:
            continue
        chunks.append(str(text))
    return "\n".join(chunks).strip()


def _summarize_one(
    job_id: str,
    description_text: str,
    company: str | None,
    *,
    client: httpx.Client,
    api_key: str,
    model: str,
) -> JobSummaryOut:
    text = (description_text or "").strip()
    if not text or text == "No description provided.":
        return JobSummaryOut(id=job_id, description="", salary=None, error=None)

    truncated = text[:_MAX_DESC_CHARS]
    company_text = (company or "").strip()
    # Pass company + description as structured plain text context.
    user_msg = (
        f"Company: {company_text}\n\nJob description:\n{truncated}"
        if company_text
        else truncated
    )
    try:
        response = client.post(
            f"{_GEMINI_BASE_URL}/models/{model}:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "system_instruction": {
                    "parts": [{"text": _SYSTEM_SUMMARY_WITH_SEARCH}]
                },
                "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 900,
                },
            },
        )
        response.raise_for_status()
        payload = response.json()
        p1_prompt, p1_completion, p1_total = _extract_usage_counts(payload)
        print(
            f"[llm][{job_id}] prompt1 tokens "
            f"prompt={p1_prompt} completion={p1_completion} total={p1_total}"
        )
        content = _extract_candidate_text(payload)
        description, salary, office_location_toronto = _parse_llm_json(content)

        return JobSummaryOut(
            id=job_id,
            description=description,
            salary=salary,
            office_location_toronto=office_location_toronto,
            error=None,
        )
    except httpx.HTTPStatusError as e:
        body = ""
        try:
            body = e.response.text
        except Exception:
            body = ""
        err = f"HTTP {e.response.status_code}: {body[:350]}".strip()
        return JobSummaryOut(
            id=job_id,
            description="",
            salary=None,
            office_location_toronto=None,
            error=err[:500],
        )
    except Exception as e:
        return JobSummaryOut(
            id=job_id,
            description="",
            salary=None,
            office_location_toronto=None,
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

    client = httpx.Client(timeout=90.0)
    out: list[JobSummaryOut] = []
    last_call_started_at: float | None = None

    try:
        for job in jobs:
            if last_call_started_at is not None:
                elapsed = time.monotonic() - last_call_started_at
                remaining = _LLM_CALL_INTERVAL_SECONDS - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)
            last_call_started_at = time.monotonic()
            out.append(
                await asyncio.to_thread(
                    _summarize_one,
                    job.id,
                    job.description,
                    job.company,
                    client=client,
                    api_key=api_key,
                    model=model,
                )
            )
    finally:
        client.close()

    return out
