"""Normalize JSearch payloads to API job DTOs (mirrors frontend display logic)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


def _employer_junk(name: str) -> bool:
    if not name or not str(name).strip():
        return False
    return bool(re.search(r"posting\s*date", str(name), re.I))


def _company_from_title(title: str | None) -> str | None:
    if not title or not str(title).strip():
        return None
    parts = [p.strip() for p in re.split(r"\s+-\s+", str(title).strip()) if p.strip()]
    if len(parts) >= 3:
        return parts[1]
    return None


def _format_location(raw: dict[str, Any]) -> str:
    loc = raw.get("job_location")
    if loc and str(loc).strip():
        return str(loc).strip()
    parts = [
        p
        for p in (
            raw.get("job_city"),
            raw.get("job_state"),
            raw.get("job_country"),
        )
        if p and str(p).strip()
    ]
    return ", ".join(str(p).strip() for p in parts) or "Location not listed"


def display_company(raw: dict[str, Any]) -> str:
    name = raw.get("employer_name")
    if name and str(name).strip() and not _employer_junk(str(name).strip()):
        return str(name).strip()
    from_title = _company_from_title(raw.get("job_title"))
    if from_title:
        return from_title
    return "Company not listed"


def listing_source(raw: dict[str, Any]) -> str | None:
    pub = raw.get("job_publisher")
    if not pub or not str(pub).strip():
        return None
    name = raw.get("employer_name")
    has_company = (
        name and str(name).strip() and not _employer_junk(str(name))
    ) or bool(_company_from_title(raw.get("job_title")))
    if has_company:
        return None
    return str(pub).strip()


def _salary_period_suffix(period: str | None) -> str:
    if not period or not str(period).strip():
        return ""
    p = str(period).strip().upper()
    if p in ("YEAR", "YEARLY"):
        return "/yr"
    if p in ("HOUR", "HOURLY"):
        return "/hr"
    if p in ("MONTH", "MONTHLY"):
        return "/mo"
    if p in ("WEEK", "WEEKLY"):
        return "/wk"
    if p in ("DAY", "DAILY"):
        return "/day"
    return f"/{p.lower()}"


def _money(value: float, currency: str | None) -> str:
    code = "USD"
    if currency and re.match(r"^[A-Z]{3}$", str(currency).strip(), re.I):
        code = str(currency).strip().upper()
    try:
        v = int(round(value))
        if code == "USD":
            return f"${v:,}"
        return f"{v:,} {code}"
    except Exception:
        return f"{value}{(' ' + currency) if currency else ''}"


def format_salary_display(raw: dict[str, Any]) -> str | None:
    currency = raw.get("job_salary_currency")
    cur = str(currency).strip() if currency else None
    suffix = _salary_period_suffix(
        str(raw.get("job_salary_period")).strip()
        if raw.get("job_salary_period")
        else None
    )

    def num(key: str) -> float | None:
        v = raw.get(key)
        if v is None:
            return None
        try:
            f = float(v)
            return f if f > 0 and f == f else None  # not NaN
        except (TypeError, ValueError):
            return None

    mn = num("job_min_salary")
    mx = num("job_max_salary")
    med = num("job_median_salary")

    if mn is not None and mx is not None:
        if abs(mn - mx) < 0.005:
            return f"{_money(mn, cur)}{suffix}"
        return f"{_money(mn, cur)} – {_money(mx, cur)}{suffix}"
    if mn is not None:
        return f"{_money(mn, cur)}{suffix}"
    if mx is not None:
        return f"{_money(mx, cur)}{suffix}"
    if med is not None:
        return f"{_money(med, cur)}{suffix} (median)"
    return None


def _format_posted_dt(dt: datetime) -> str:
    return dt.strftime("%b ") + str(dt.day) + dt.strftime(", %Y")


def _normalize_href(url: str | None) -> str | None:
    if not url or not str(url).strip():
        return None
    s = str(url).strip()
    if s.startswith("//"):
        return "https:" + s
    low = s.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return s
    return None


def extract_apply_options(raw: dict[str, Any]) -> list[dict[str, str]]:
    """Build deduplicated apply links from JSearch job or job-details payload."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(publisher: str, link: str | None) -> None:
        href = _normalize_href(link)
        if not href or href in seen:
            return
        seen.add(href)
        pub = publisher.strip() if publisher and str(publisher).strip() else "Apply"
        out.append({"publisher": pub, "applyLink": href})

    main = raw.get("job_apply_link")
    if main:
        pub = raw.get("job_publisher") or "Apply"
        add(str(pub), str(main))

    opts = raw.get("apply_options")
    if isinstance(opts, list):
        for o in opts:
            if not isinstance(o, dict):
                continue
            pub = o.get("publisher") or o.get("job_publisher") or "Apply"
            link = (
                o.get("apply_link")
                or o.get("applyLink")
                or o.get("link")
            )
            if link:
                add(str(pub), str(link))

    return out


def raw_job_from_jsearch_detail_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    if payload.get("job_id") is not None or payload.get("job_title"):
        return payload
    return {}


def format_posted_display(raw: dict[str, Any]) -> str | None:
    iso = raw.get("job_posted_at_datetime_utc")
    if not iso or not str(iso).strip():
        return None
    s = str(iso).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return _format_posted_dt(dt)
    except ValueError:
        try:
            dt = datetime.fromisoformat(s.replace(" ", "T"))
            return _format_posted_dt(dt)
        except ValueError:
            return None


def normalize_job(raw: dict[str, Any], index: int) -> dict[str, Any]:
    jid = raw.get("job_id")
    job_id = str(jid).strip() if jid else None
    title = str(raw.get("job_title") or "").strip() or "Untitled role"
    desc = str(raw.get("job_description") or "").strip() or "No description provided."

    posted_iso = None
    p = raw.get("job_posted_at_datetime_utc")
    if p and str(p).strip():
        posted_iso = str(p).strip()

    return {
        "id": job_id or f"{title}-{index}",
        "title": title,
        "company": display_company(raw),
        "location": _format_location(raw),
        "postedAt": posted_iso,
        "postedDisplay": format_posted_display(raw),
        "description": desc,
        "salaryDisplay": format_salary_display(raw),
        "listingSource": listing_source(raw),
        "jobPublisher": (
            str(raw.get("job_publisher")).strip() if raw.get("job_publisher") else None
        ),
        "jobMinSalary": raw.get("job_min_salary"),
        "jobMaxSalary": raw.get("job_max_salary"),
        "jobMedianSalary": raw.get("job_median_salary"),
        "jobSalaryCurrency": raw.get("job_salary_currency"),
        "jobSalaryPeriod": raw.get("job_salary_period"),
        "jobCity": raw.get("job_city"),
        "jobState": raw.get("job_state"),
        "jobCountry": raw.get("job_country"),
        "jobLocation": raw.get("job_location"),
        "employerName": raw.get("employer_name"),
        "applyOptions": extract_apply_options(raw),
    }
