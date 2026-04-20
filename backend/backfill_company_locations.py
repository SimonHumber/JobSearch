from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx
import psycopg

from app.config import get_settings

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_SYSTEM_PROMPT = (
    "Return strict JSON only with one key: 'address'. "
    "Find the Greater Toronto Area office street address for the provided company. "
    "Address must include street number, street name, and city. "
    "If unknown, return null."
)
_RETRY_ATTEMPTS = 3
_RETRY_BASE_SLEEP_SECONDS = 2.0
_BATCH_COMMIT_EVERY = 5
_CHECKPOINT_PATH = (
    Path(__file__).resolve().with_name(".backfill_company_locations_checkpoint.json")
)
_LLM_SKIP_COMPANIES = {
    "G2i Inc.",
    "School Result",
    "CloudDevs",
    "Carta, Inc.",
    "TryClover Inc.",
    "Marqeta",
    "Canonical",
    "Rivian and VW Group Technology",
    "Hive.co",
    "Motive",
    "Wayfair",
    "Great Value Hiring",
    "confidential",
    "Decoda Health",
    "Partner Experience XML Feed",
    "Vanta",
    "Various Employers",
    "Klue",
}


def _load_checkpoint() -> int | None:
    if not _CHECKPOINT_PATH.exists():
        return None
    try:
        data = json.loads(_CHECKPOINT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("last_completed_company_id")
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _save_checkpoint(last_completed_company_id: int) -> None:
    payload = {
        "last_completed_company_id": int(last_completed_company_id),
        "updated_at_unix": int(time.time()),
    }
    _CHECKPOINT_PATH.write_text(
        json.dumps(payload, ensure_ascii=True), encoding="utf-8"
    )


def _clear_checkpoint() -> None:
    if _CHECKPOINT_PATH.exists():
        _CHECKPOINT_PATH.unlink()


def _strip_json_fence(content: str) -> str:
    raw = content.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, count=1, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```\s*$", "", raw, count=1)
    return raw.strip()


def _parse_address_json(content: str) -> str | None:
    raw = _strip_json_fence(content)
    decoder = json.JSONDecoder()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        if start == -1:
            return None
        try:
            data, _ = decoder.raw_decode(raw[start:])
        except Exception:
            return None
    if not isinstance(data, dict):
        return None
    value = data.get("address")
    if value is None:
        return None
    address = str(value).strip()
    if not address:
        return None
    lowered = address.lower()
    if lowered in {"...", "n/a", "na", "unknown", "null", "none"}:
        return None
    return address


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
    out: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if text is None:
            continue
        out.append(str(text))
    return "\n".join(out).strip()


def _find_address_with_gemma(
    *,
    client: httpx.Client,
    api_key: str,
    model: str,
    company_name: str,
) -> str | None:
    last_error: Exception | None = None
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            response = client.post(
                f"{_GEMINI_BASE_URL}/models/{model}:generateContent",
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json={
                    "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": (
                                        "Company: "
                                        f"{company_name}\n\n"
                                        "Find the Toronto office street address."
                                    )
                                }
                            ],
                        }
                    ],
                    "tools": [{"google_search": {}}],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 220},
                },
            )
            if response.status_code != 200:
                print(
                    f"[gemma] {company_name}: HTTP {response.status_code} "
                    f"(attempt {attempt}/{_RETRY_ATTEMPTS})"
                )
                if attempt < _RETRY_ATTEMPTS:
                    time.sleep(_RETRY_BASE_SLEEP_SECONDS * attempt)
                continue
            payload = response.json()
            content = _extract_candidate_text(payload)
            return _parse_address_json(content)
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            last_error = exc
            print(
                f"[gemma] {company_name}: request failed "
                f"(attempt {attempt}/{_RETRY_ATTEMPTS}): {exc}"
            )
            if attempt < _RETRY_ATTEMPTS:
                time.sleep(_RETRY_BASE_SLEEP_SECONDS * attempt)
    if last_error:
        print(f"[gemma] {company_name}: giving up after retries")
    return None


def _geocode_address(
    *,
    client: httpx.Client,
    map_api_key: str,
    address: str,
) -> tuple[float, float] | None:
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            response = client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": address, "key": map_api_key},
            )
            if response.status_code != 200:
                if attempt < _RETRY_ATTEMPTS:
                    time.sleep(_RETRY_BASE_SLEEP_SECONDS * attempt)
                    continue
                return None
            payload = response.json()
            status = str(payload.get("status") or "")
            if status != "OK":
                return None
            results = payload.get("results")
            if not isinstance(results, list) or not results:
                return None
            first = results[0]
            if not isinstance(first, dict):
                return None
            geometry = first.get("geometry")
            if not isinstance(geometry, dict):
                return None
            location = geometry.get("location")
            if not isinstance(location, dict):
                return None
            lat = location.get("lat")
            lng = location.get("lng")
            if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
                return None
            return float(lat), float(lng)
        except (httpx.TimeoutException, httpx.RequestError):
            if attempt < _RETRY_ATTEMPTS:
                time.sleep(_RETRY_BASE_SLEEP_SECONDS * attempt)
                continue
            return None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill company address + coordinates using Gemma and geocoding."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum number of company rows to process.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print updates without writing to database.",
    )
    parser.add_argument(
        "--start-after-id",
        type=int,
        default=None,
        help="Start strictly after this company id (overrides checkpoint).",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore saved checkpoint and start from the beginning.",
    )
    parser.add_argument(
        "--clear-checkpoint",
        action="store_true",
        help="Delete checkpoint and exit.",
    )
    args = parser.parse_args()

    if args.clear_checkpoint:
        _clear_checkpoint()
        print(f"[run] Cleared checkpoint: {_CHECKPOINT_PATH}")
        return

    settings = get_settings()
    db_url = settings.postgres_url
    if not db_url:
        raise RuntimeError("Set SUPABASE_URL (or DATABASE_URL) in backend/.env.")

    gemini_key = settings.google_api_key.strip()
    if not gemini_key:
        raise RuntimeError("GOOGLE_API_KEY is required in backend/.env.")

    map_api_key = settings.map_api_key.strip()
    if not map_api_key:
        raise RuntimeError("MAP_API_KEY is required in backend/.env.")

    model = settings.gemini_model.strip() or "gemma-4-31b-it"
    print(f"[run] Using model: {model}")

    if args.start_after_id is not None:
        start_after_id = max(0, int(args.start_after_id))
    elif args.no_resume:
        start_after_id = 0
    else:
        start_after_id = _load_checkpoint() or 0

    if start_after_id > 0:
        print(f"[run] Resuming from company id > {start_after_id}")
    else:
        print("[run] Starting from beginning (no checkpoint resume)")

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, address, lat, long
                FROM companies
                WHERE id > %s
                ORDER BY id ASC
                LIMIT %s;
                """,
                (start_after_id, max(1, args.limit)),
            )
            rows = cur.fetchall()

            if not rows:
                print("[run] No companies found.")
                return

            print(f"[run] Processing up to {len(rows)} companies")
            gemma_client = httpx.Client(timeout=120.0)
            geo_client = httpx.Client(timeout=20.0)
            updated = 0
            failures = 0
            aborted_due_to_db_loss = False
            try:
                for row in rows:
                    try:
                        company_id = int(row[0])
                        company_name = str(row[1] or "").strip()
                        current_address = str(row[2] or "").strip() or None
                        current_lat = row[3]
                        current_long = row[4]

                        if not company_name:
                            if not args.dry_run:
                                _save_checkpoint(company_id)
                            continue

                        address = current_address
                        if not address:
                            if company_name in _LLM_SKIP_COMPANIES:
                                print(
                                    f"[skip] {company_name}: in LLM skip list (known no-address)"
                                )
                                if not args.dry_run:
                                    _save_checkpoint(company_id)
                                continue
                            address = _find_address_with_gemma(
                                client=gemma_client,
                                api_key=gemini_key,
                                model=model,
                                company_name=company_name,
                            )

                        if not address:
                            print(f"[skip] {company_name}: no address found")
                            if not args.dry_run:
                                _save_checkpoint(company_id)
                            continue

                        coords = _geocode_address(
                            client=geo_client, map_api_key=map_api_key, address=address
                        )
                        if coords is None:
                            print(f"[skip] {company_name}: geocode failed")
                            if not args.dry_run:
                                _save_checkpoint(company_id)
                            continue
                        lat, lng = coords

                        changed = (
                            (current_address or "") != address
                            or current_lat is None
                            or current_long is None
                        )
                        if not changed:
                            if not args.dry_run:
                                _save_checkpoint(company_id)
                            continue

                        print(
                            f"[update] {company_name} -> {address} "
                            f"({lat:.6f}, {lng:.6f})"
                        )
                        if not args.dry_run:
                            cur.execute(
                                """
                                UPDATE companies
                                SET address = %s, lat = %s, long = %s
                                WHERE id = %s;
                                """,
                                (address, lat, lng, company_id),
                            )
                        updated += 1
                        if (
                            not args.dry_run
                            and updated > 0
                            and updated % _BATCH_COMMIT_EVERY == 0
                        ):
                            conn.commit()
                            print(f"[run] Intermediate commit at {updated} updates")
                        if not args.dry_run:
                            _save_checkpoint(company_id)
                    except Exception as exc:
                        failures += 1
                        print(f"[error] Row processing failed: {exc}")
                        text = str(exc).lower()
                        if (
                            "connection is lost" in text
                            or "server closed the connection" in text
                        ):
                            aborted_due_to_db_loss = True
                            print(
                                "[run] Database connection lost; stopping early to preserve checkpoint"
                            )
                            break
                        continue
                else:
                    # Completed all rows without early break.
                    pass
            finally:
                gemma_client.close()
                geo_client.close()

            if args.dry_run:
                conn.rollback()
                print(
                    f"[done] Dry run only. Candidate updates: {updated}, failures: {failures}"
                )
                if not args.no_resume:
                    print(f"[done] Checkpoint unchanged: {_CHECKPOINT_PATH}")
            else:
                if aborted_due_to_db_loss:
                    print(
                        f"[done] Aborted after DB loss. Updates before abort: {updated}, failures: {failures}"
                    )
                    print(f"[done] Resume next run from checkpoint: {_CHECKPOINT_PATH}")
                    return
                conn.commit()
                print(f"[done] Updated rows: {updated}, failures: {failures}")
                _clear_checkpoint()
                print("[done] Completed batch; checkpoint cleared")


if __name__ == "__main__":
    main()
