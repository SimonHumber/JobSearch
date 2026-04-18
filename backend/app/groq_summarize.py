"""Batch job-description summaries via Groq."""

from __future__ import annotations

import asyncio
import json
import time
import re

from groq import Groq

from app.schemas import JobDescriptionIn, JobSummaryOut

_MAX_DESC_CHARS = 24_000
_LLM_CALL_INTERVAL_SECONDS = 1.0

_SYSTEM_SUMMARY_NO_BROWSER = (
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
    "3. For 'office_location_toronto': use only the provided job text. "
    "Do not call tools or browse externally. Return only a Toronto office STREET ADDRESS "
    "(street number + street name + Toronto) when explicit. "
    "If not found, return null."
)

_SYSTEM_OFFICE_WITH_BROWSER = (
    "Return a valid JSON object with exactly one key: 'office_location_toronto'. "
    "Keep the output strictly JSON; no preamble or conversational filler."
    "You may use browser search tools.\n\n"
    "Find the employer's Toronto office STREET ADDRESS (not broad area) using the provided context and browser search.\n"
    "Return a precise address-like string (street number + street name, with Toronto) when found.\n"
    "If only broad location is found, return null."
)


def _strip_json_fence(content: str) -> str:
    raw = content.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, count=1, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```\s*$", "", raw, count=1)
    return raw.strip()


def _parse_llm_json(content: str) -> tuple[str, str | None, str | None]:
    raw = _strip_json_fence(content)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        data = json.loads(raw[start : end + 1])
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


def _looks_like_toronto_address(value: str | None) -> bool:
    if not value:
        return False
    s = value.strip()
    if not s:
        return False
    has_number = bool(re.search(r"\b\d{1,6}\b", s))
    has_street_word = bool(
        re.search(
            r"\b(street|st\.?|avenue|ave\.?|road|rd\.?|boulevard|blvd\.?|drive|dr\.?|lane|ln\.?|way|court|ct\.?|quay|place|pl\.?)\b",
            s,
            flags=re.IGNORECASE,
        )
    )
    has_toronto = bool(re.search(r"\btoronto\b", s, flags=re.IGNORECASE))
    return has_number and has_street_word and has_toronto


def _extract_message_content(choice: object) -> str:
    content = str(getattr(choice, "content", "") or "").strip()
    if not content:
        content = str(getattr(choice, "reasoning", "") or "").strip()
    return content


def _parse_office_only_json(content: str) -> str | None:
    raw = _strip_json_fence(content)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        return None
    office = data.get("office_location_toronto")
    if office is None:
        return None
    office_text = str(office).strip() or None
    return office_text


def _extract_usage_counts(completion: object) -> tuple[int | None, int | None, int | None]:
    usage = getattr(completion, "usage", None)
    if usage is None:
        return None, None, None
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    return prompt_tokens, completion_tokens, total_tokens


def _summarize_one(
    job_id: str,
    description_text: str,
    company: str | None,
    *,
    client: Groq,
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
    model_name = (model or "").strip().lower()
    is_gpt_oss = "gpt-oss" in model_name
    try:
        # Pass 1: summarize + salary; office only from provided text (no browsing).
        summary_kwargs: dict[str, object] = {}
        if is_gpt_oss:
            summary_kwargs["response_format"] = {"type": "json_object"}
        summary_completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_SUMMARY_NO_BROWSER},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=900,
            **summary_kwargs,
        )
        p1_prompt, p1_completion, p1_total = _extract_usage_counts(summary_completion)
        print(
            f"[llm][{job_id}] prompt1 tokens "
            f"prompt={p1_prompt} completion={p1_completion} total={p1_total}"
        )
        choice = summary_completion.choices[0].message
        content = _extract_message_content(choice)
        try:
            description, salary, office_location_toronto = _parse_llm_json(content)
        except Exception:
            reasoning = str(getattr(choice, "reasoning", "") or "").strip()
            if reasoning and reasoning != content:
                description, salary, office_location_toronto = _parse_llm_json(
                    reasoning
                )
            else:
                raise

        # Keep only address-like office values from pass 1.
        if office_location_toronto and not _looks_like_toronto_address(
            office_location_toronto
        ):
            office_location_toronto = None

        # Pass 2: run focused browser-search lookup only when office is null.
        if office_location_toronto is None:
            company_text = (company or "").strip() or "Unknown"
            office_prompt = (
                "Company context:\n"
                f"{company_text}\n\n"
                "Find a Toronto office street address for this employer."
            )
            try:
                office_completion = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_OFFICE_WITH_BROWSER},
                        {"role": "user", "content": office_prompt},
                    ],
                    tools=[{"type": "browser_search"}],
                    temperature=0.0,
                    max_tokens=220,
                )
                p2_prompt, p2_completion, p2_total = _extract_usage_counts(
                    office_completion
                )
                print(
                    f"[llm][{job_id}] prompt2 tokens "
                    f"prompt={p2_prompt} completion={p2_completion} total={p2_total}"
                )
                office_choice = office_completion.choices[0].message
                office_content = _extract_message_content(office_choice)
                office_from_web = _parse_office_only_json(office_content)
                office_location_toronto = (
                    office_from_web
                    if _looks_like_toronto_address(office_from_web)
                    else None
                )
            except Exception:
                office_location_toronto = None

        return JobSummaryOut(
            id=job_id,
            description=description,
            salary=salary,
            office_location_toronto=office_location_toronto,
            error=None,
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

    client = Groq(api_key=api_key)
    out: list[JobSummaryOut] = []
    last_call_started_at: float | None = None

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
                model=model,
            )
        )

    return out
