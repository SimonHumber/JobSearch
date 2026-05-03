"""Re-run summarization for job_postings whose previous attempt failed.

Targets rows where ``payload->>'aiSummaryError'`` is non-empty (typically the
HTTP 500 / INTERNAL errors from Gemini).

For each errored row:

1. Check the ``companies`` table first. If the company already has an
   address, use it directly and call Gemini with a plain (non-grounded)
   prompt for just the description + salary. This is faster, cheaper, and
   preserves any curated addresses.
2. Otherwise call with Google Search grounding (non-Gemma models only:
   ``tools: [{"google_search": {}}]``) so the model can look up the company's
   Greater Toronto Area office. Gemma models use the same prompts but without
   tools (API limitation).

Either way, writes the regenerated summary/salary/office back into the JSONB
payload and clears ``aiSummaryError``.

Usage::

    python retry_errored_summaries.py                    # retry everything
    python retry_errored_summaries.py --only-http-500    # just the 500s
    python retry_errored_summaries.py --dry-run          # preview, no DB writes
    python retry_errored_summaries.py --model gemma-4-31b-it
"""

from __future__ import annotations

import argparse
import json
import re
import time
from typing import Any

import httpx
import psycopg

from app.config import get_settings

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def _model_supports_google_search_grounding(model: str) -> bool:
    """Gemma models reject ``tools: [{"google_search": {}}]`` on this API."""
    return "gemma" not in model.lower()

_MAX_DESC_CHARS = 24_000
_RETRY_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_RETRY_MAX_ATTEMPTS = 4
_RETRY_BACKOFF_BASE_SECONDS = 1.5
_CALL_INTERVAL_SECONDS = 0.5

# Two prompt variants. We use the NO_SEARCH version when the companies table
# already has an address for this company — faster, cheaper, and avoids
# overriding a curated address with a web-search guess.
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
    "2. For 'description': provide a single string containing a summary of the "
    "role followed by a list of qualifications. Use standard dashes (-) for "
    "bullets and newline characters (\\n) for spacing. Avoid all Markdown "
    "formatting like bolding (**) or headers (#)."
    "\n\n"
    "3. For 'office_location_toronto': prefer an explicit street address from "
    "the job description if one is present. Otherwise, you MAY use web search "
    "to find the company's Greater Toronto Area office street address "
    "(street number + street name + city). If the company has no known GTA "
    "office, return null. Do NOT invent addresses."
)

_SYSTEM_SUMMARY_NO_SEARCH = (
    "Return a valid JSON object with exactly two keys: "
    "'description' and 'salary'. "
    "Keep the output strictly JSON; no preamble or conversational filler."
    "\n\n"
    "1. 'salary':\n"
    "- Extract the exact salary text ONLY if it contains digits (0-9).\n"
    "- If no digits are present, output null.\n"
    "- No other text is allowed.\n"
    "\n"
    "2. For 'description': provide a single string containing a summary of the "
    "role followed by a list of qualifications. Use standard dashes (-) for "
    "bullets and newline characters (\\n) for spacing. Avoid all Markdown "
    "formatting like bolding (**) or headers (#)."
)


def _strip_json_fence(content: str) -> str:
    raw = content.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, count=1, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```\s*$", "", raw, count=1)
    return raw.strip()


def _parse_summary_json(
    content: str,
    *,
    expect_office: bool,
) -> tuple[str, str | None, str | None]:
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
    office_location: str | None = None
    if expect_office:
        office = data.get("office_location_toronto")
        if office is not None and not (
            isinstance(office, str) and not office.strip()
        ):
            office_location = str(office).strip() or None
            if office_location is not None:
                low = office_location.lower()
                if low in {"...", "n/a", "na", "unknown", "null", "none"}:
                    office_location = None
    return description, salary, office_location


def _extract_candidate_text(payload: dict[str, Any]) -> str:
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
    *,
    client: httpx.Client,
    api_key: str,
    model: str,
    job_id: str,
    company: str | None,
    description: str,
    use_web_search: bool,
) -> tuple[str, str | None, str | None, str | None]:
    """Returns (description, salary, office_location_toronto, error).

    When ``use_web_search`` is True, the model is allowed to look up the
    company's GTA office address via Google Search grounding. When False, the
    office field is omitted from the prompt and always returned as None (the
    caller is expected to supply the address from the companies table).
    """
    text = (description or "").strip()
    if not text or text == "No description provided.":
        return "", None, None, None

    truncated = text[:_MAX_DESC_CHARS]
    company_text = (company or "").strip()
    user_msg = (
        f"Company: {company_text}\n\nJob description:\n{truncated}"
        if company_text
        else truncated
    )

    system_prompt = (
        _SYSTEM_SUMMARY_WITH_SEARCH if use_web_search else _SYSTEM_SUMMARY_NO_SEARCH
    )
    request_json: dict[str, Any] = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 900,
        },
    }
    if use_web_search and _model_supports_google_search_grounding(model):
        request_json["tools"] = [{"google_search": {}}]

    last_error = ""
    for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
        retriable = False
        try:
            response = client.post(
                f"{_GEMINI_BASE_URL}/models/{model}:generateContent",
                headers={
                    "x-goog-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json=request_json,
            )
            response.raise_for_status()
            payload = response.json()
            content = _extract_candidate_text(payload)
            desc, salary, office = _parse_summary_json(
                content, expect_office=use_web_search
            )
            return desc, salary, office, None
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            body = ""
            try:
                body = e.response.text
            except Exception:
                body = ""
            last_error = f"HTTP {status}: {body[:350]}".strip()
            retriable = status in _RETRY_STATUS_CODES
        except (httpx.RequestError, httpx.TimeoutException) as e:
            last_error = f"{type(e).__name__}: {e}"[:500]
            retriable = True
        except Exception as e:
            return "", None, None, str(e)[:500]

        if not retriable or attempt >= _RETRY_MAX_ATTEMPTS:
            break

        backoff = _RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
        print(
            f"[retry][{job_id}] attempt {attempt}/{_RETRY_MAX_ATTEMPTS} failed "
            f"({last_error[:120]}); retrying in {backoff:.1f}s"
        )
        time.sleep(backoff)

    return "", None, None, (last_error[:500] or "Unknown error")


def _load_known_addresses(conn: psycopg.Connection) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT name, address FROM companies
            WHERE address IS NOT NULL AND btrim(address) <> '';
            """
        )
        rows = cur.fetchall()
    out: dict[str, str] = {}
    for row in rows:
        name = str(row[0] or "").strip()
        addr = str(row[1] or "").strip()
        if name and addr:
            out[name] = addr
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Re-run summarization with Google Search grounding for "
            "job_postings whose previous attempt recorded aiSummaryError."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max rows to process (0 = no limit).",
    )
    parser.add_argument(
        "--only-http-500",
        action="store_true",
        help="Only retry rows whose error text starts with 'HTTP 500'.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be updated without writing to the DB.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Model id (default: GEMINI_MODEL / gemma-4-31b-it). "
            "Google Search grounding is only sent for non-Gemma models."
        ),
    )
    args = parser.parse_args()

    settings = get_settings()
    db_url = settings.postgres_url
    if not db_url:
        raise RuntimeError("Set SUPABASE_URL (or DATABASE_URL) in backend/.env.")

    api_key = settings.google_api_key.strip()
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is required.")

    model = (args.model or settings.gemini_model).strip() or "gemma-4-31b-it"
    print(f"[retry] Using model '{model}'")

    where_parts = [
        "payload->>'aiSummaryError' IS NOT NULL",
        "payload->>'aiSummaryError' <> ''",
    ]
    if args.only_http_500:
        where_parts.append("payload->>'aiSummaryError' LIKE 'HTTP 500%'")
    where_sql = " AND ".join(where_parts)

    limit_clause = (
        f" LIMIT {int(args.limit)}" if args.limit and args.limit > 0 else ""
    )
    select_sql = (
        "SELECT id, payload FROM job_postings "
        f"WHERE {where_sql} ORDER BY id{limit_clause};"
    )

    with psycopg.connect(db_url, prepare_threshold=None) as conn:
        known_addresses = _load_known_addresses(conn)
        print(
            f"[retry] Loaded {len(known_addresses)} known company address(es) "
            "from companies table"
        )

        with conn.cursor() as cur:
            cur.execute(select_sql)
            rows = cur.fetchall()

        print(f"[retry] Found {len(rows)} errored posting(s) to retry")
        if not rows:
            return

        client = httpx.Client(timeout=120.0)
        fixed = 0
        still_failing = 0
        prefilled_address_count = 0
        last_call = 0.0
        try:
            for job_id, payload in rows:
                if not isinstance(payload, dict):
                    print(f"[retry][{job_id}] payload not a dict; skipping")
                    continue
                company = str(payload.get("company") or "").strip() or None
                description = str(payload.get("description") or "")

                known_address = (
                    known_addresses.get(company) if company else None
                )
                use_web_search = known_address is None

                elapsed = time.monotonic() - last_call
                if elapsed < _CALL_INTERVAL_SECONDS:
                    time.sleep(_CALL_INTERVAL_SECONDS - elapsed)
                last_call = time.monotonic()

                new_desc, new_salary, llm_office, err = _summarize_one(
                    client=client,
                    api_key=api_key,
                    model=model,
                    job_id=str(job_id),
                    company=company,
                    description=description,
                    use_web_search=use_web_search,
                )

                # Known address from companies table always wins over LLM output.
                if known_address:
                    new_office: str | None = known_address
                    prefilled_address_count += 1
                else:
                    new_office = llm_office

                new_payload = dict(payload)
                if err:
                    new_payload["aiSummaryError"] = err
                    new_payload["aiSummary"] = None
                    still_failing += 1
                    print(f"[retry][{job_id}] still failing: {err[:160]}")
                else:
                    new_payload["aiSummary"] = new_desc or None
                    if new_salary and not str(
                        payload.get("salaryDisplay") or ""
                    ).strip():
                        new_payload["salaryDisplay"] = new_salary
                    new_payload["aiOfficeLocationToronto"] = new_office
                    new_payload["aiSummaryError"] = None
                    fixed += 1
                    addr_source = (
                        "companies"
                        if known_address
                        else ("search" if new_office else "none")
                    )
                    print(
                        f"[retry][{job_id}] ok — "
                        f"office={new_office or '-'} ({addr_source}) "
                        f"salary={new_salary or '-'}"
                    )

                if args.dry_run:
                    continue

                try:
                    with conn.cursor() as upd:
                        upd.execute(
                            "UPDATE job_postings "
                            "SET payload = %s::jsonb WHERE id = %s;",
                            (
                                json.dumps(new_payload, ensure_ascii=False),
                                job_id,
                            ),
                        )
                        # Keep companies.address in sync only when the retry
                        # discovered a new address via web search. If the
                        # address was already in the companies table we'd
                        # just be echoing it back.
                        if new_office and company and known_address is None:
                            upd.execute(
                                """
                                INSERT INTO companies (name, address)
                                VALUES (%s, %s)
                                ON CONFLICT (name) DO UPDATE
                                SET address = COALESCE(
                                    EXCLUDED.address, companies.address
                                );
                                """,
                                (company, new_office),
                            )
                            known_addresses[company] = new_office
                    conn.commit()
                except Exception as exc:
                    conn.rollback()
                    print(f"[retry][{job_id}] DB write failed: {exc}")
        finally:
            client.close()

        print(
            f"[done] fixed={fixed} still_failing={still_failing} "
            f"total_processed={len(rows)} "
            f"addresses_from_companies_table={prefilled_address_count}"
        )


if __name__ == "__main__":
    main()
