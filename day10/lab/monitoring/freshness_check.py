"""
Kiểm tra freshness từ manifest pipeline.

Quy ước trạng thái:
- PASS: snapshot dữ liệu còn trong SLA.
- WARN: đã vượt SLA nhưng còn trong grace window để chạy lại pipeline.
- FAIL: manifest lỗi/mất hoặc snapshot vượt grace window.
"""

from __future__ import annotations

import json
from json import JSONDecodeError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple


def parse_iso(ts: str) -> datetime | None:
    text = (ts or "").strip()
    if not text:
        return None
    try:
        # Cho phép "2026-04-10T08:00:00" không có timezone.
        if text.endswith("Z"):
            text = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _iter_exported_at_values(value: Any) -> Iterable[str]:
    """Tìm các giá trị exported_at trong cleaned summary nếu manifest có nhúng."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "exported_at" and child:
                yield str(child)
            elif isinstance(child, (dict, list, tuple)):
                yield from _iter_exported_at_values(child)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_exported_at_values(item)


def _latest_cleaned_summary_export(data: Dict[str, Any]) -> tuple[str | None, str | None]:
    candidates = []
    for key in ("cleaned_summary", "cleaned_rows", "cleaned_records_sample", "cleaned_sample"):
        for raw in _iter_exported_at_values(data.get(key)):
            dt = parse_iso(raw)
            if dt is not None:
                candidates.append((dt, raw))

    if not candidates:
        return None, None
    _, raw = max(candidates, key=lambda item: item[0])
    return raw, "cleaned_summary.exported_at"


def _manifest_freshness_timestamp(data: Dict[str, Any]) -> tuple[str | None, str | None]:
    latest_exported = data.get("latest_exported_at")
    if latest_exported:
        return str(latest_exported), "latest_exported_at"
    return _latest_cleaned_summary_export(data)


def check_manifest_freshness(
    manifest_path: Path,
    *,
    sla_hours: float = 24.0,
    warn_after_hours: float | None = None,
    now: datetime | None = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Trả về ("PASS" | "WARN" | "FAIL", detail dict).

    Đọc trường `latest_exported_at` hoặc max `exported_at` trong cleaned summary.
    `run_timestamp` chỉ được đưa vào detail để debug, không dùng thay watermark dữ liệu.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    warn_after_hours = warn_after_hours if warn_after_hours is not None else sla_hours * 2
    if sla_hours <= 0 or warn_after_hours < sla_hours:
        return "FAIL", {
            "reason": "invalid_freshness_threshold",
            "sla_hours": sla_hours,
            "warn_after_hours": warn_after_hours,
        }

    if not manifest_path.is_file():
        return "FAIL", {"reason": "manifest_missing", "path": str(manifest_path)}

    try:
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        return "FAIL", {
            "reason": "manifest_invalid_json",
            "path": str(manifest_path),
            "error": str(exc),
        }
    except OSError as exc:
        return "FAIL", {
            "reason": "manifest_read_error",
            "path": str(manifest_path),
            "error": str(exc),
        }

    if not isinstance(loaded, dict):
        return "FAIL", {
            "reason": "manifest_not_object",
            "path": str(manifest_path),
            "manifest_type": type(loaded).__name__,
        }

    data: Dict[str, Any] = loaded
    ts_raw, timestamp_field = _manifest_freshness_timestamp(data)
    dt = parse_iso(str(ts_raw)) if ts_raw else None
    if dt is None:
        return "WARN", {
            "reason": "no_data_timestamp_in_manifest",
            "path": str(manifest_path),
            "run_id": data.get("run_id"),
            "run_timestamp": data.get("run_timestamp"),
            "sla_hours": sla_hours,
            "warn_after_hours": warn_after_hours,
        }

    age_hours = (now - dt).total_seconds() / 3600.0
    detail = {
        "latest_exported_at": ts_raw,
        "timestamp_field": timestamp_field,
        "age_hours": round(age_hours, 3),
        "sla_hours": sla_hours,
        "warn_after_hours": warn_after_hours,
    }
    if age_hours < -0.083:  # Cho phép lệch clock tối đa khoảng 5 phút.
        return "WARN", {**detail, "reason": "timestamp_in_future"}
    if age_hours <= sla_hours:
        return "PASS", {**detail, "reason": "within_sla"}
    if age_hours <= warn_after_hours:
        return "WARN", {**detail, "reason": "freshness_sla_breached_within_grace"}
    return "FAIL", {**detail, "reason": "freshness_grace_window_exceeded"}
