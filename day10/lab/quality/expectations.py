"""
Expectation suite đơn giản (không bắt buộc Great Expectations).

Sinh viên có thể thay bằng GE / pydantic / custom — miễn là có halt có kiểm soát.

Người 3 (Ngô Quang Phúc) — mở rộng:
  E7  each_critical_doc_has_min_chunks   halt
  E8  no_duplicate_chunk_ids             halt
  E9  chunk_text_reasonable_length       warn
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

# Load .env để test với OPENAI_API_KEY nếu cần
load_dotenv(override=True)


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    severity: str  # "warn" | "halt"
    detail: str


def run_expectations(cleaned_rows: List[Dict[str, Any]]) -> Tuple[List[ExpectationResult], bool]:
    """
    Trả về (results, should_halt).

    should_halt = True nếu có bất kỳ expectation severity halt nào fail.
    """
    results: List[ExpectationResult] = []

    # E1: có ít nhất 1 dòng sau clean
    ok = len(cleaned_rows) >= 1
    results.append(
        ExpectationResult(
            "min_one_row",
            ok,
            "halt",
            f"cleaned_rows={len(cleaned_rows)}",
        )
    )

    # E2: không doc_id rỗng
    bad_doc = [r for r in cleaned_rows if not (r.get("doc_id") or "").strip()]
    ok2 = len(bad_doc) == 0
    results.append(
        ExpectationResult(
            "no_empty_doc_id",
            ok2,
            "halt",
            f"empty_doc_id_count={len(bad_doc)}",
        )
    )

    # E3: policy refund không được chứa cửa sổ sai 14 ngày (sau khi đã fix)
    bad_refund = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "policy_refund_v4"
        and "14 ngày làm việc" in (r.get("chunk_text") or "")
    ]
    ok3 = len(bad_refund) == 0
    results.append(
        ExpectationResult(
            "refund_no_stale_14d_window",
            ok3,
            "halt",
            f"violations={len(bad_refund)}",
        )
    )

    # E4: chunk_text đủ dài
    short = [r for r in cleaned_rows if len((r.get("chunk_text") or "")) < 8]
    ok4 = len(short) == 0
    results.append(
        ExpectationResult(
            "chunk_min_length_8",
            ok4,
            "warn",
            f"short_chunks={len(short)}",
        )
    )

    # E5: effective_date đúng định dạng ISO sau clean (phát hiện parser lỏng)
    iso_bad = [
        r
        for r in cleaned_rows
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", (r.get("effective_date") or "").strip())
    ]
    ok5 = len(iso_bad) == 0
    results.append(
        ExpectationResult(
            "effective_date_iso_yyyy_mm_dd",
            ok5,
            "halt",
            f"non_iso_rows={len(iso_bad)}",
        )
    )

    # E6: không còn marker phép năm cũ 10 ngày trên doc HR (conflict version sau clean)
    bad_hr_annual = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "hr_leave_policy"
        and "10 ngày phép năm" in (r.get("chunk_text") or "")
    ]
    ok6 = len(bad_hr_annual) == 0
    results.append(
        ExpectationResult(
            "hr_leave_no_stale_10d_annual",
            ok6,
            "halt",
            f"violations={len(bad_hr_annual)}",
        )
    )

    # ------------------------------------------------------------------
    # E7: each_critical_doc_has_min_chunks  [halt]
    # ------------------------------------------------------------------
    # Mỗi doc_id quan trọng phải còn ít nhất 1 chunk sau clean.
    # Nếu doc bị quarantine sạch → vector store sẽ không có nội dung để retrieve.
    # metric_impact: phát hiện khi toàn bộ chunk của 1 doc bị quarantine (ví dụ
    #   inject sai effective_date cho tất cả chunk của hr_leave_policy → 0 chunk còn lại).
    CRITICAL_DOC_IDS = {"policy_refund_v4", "sla_p1_2026", "hr_leave_policy", "it_helpdesk_faq"}
    doc_chunk_counts: Dict[str, int] = {}
    for r in cleaned_rows:
        did = r.get("doc_id", "")
        doc_chunk_counts[did] = doc_chunk_counts.get(did, 0) + 1

    missing_docs = [d for d in CRITICAL_DOC_IDS if doc_chunk_counts.get(d, 0) == 0]
    ok7 = len(missing_docs) == 0
    results.append(
        ExpectationResult(
            "each_critical_doc_has_min_chunks",
            ok7,
            "halt",
            f"missing_docs={missing_docs}; counts={doc_chunk_counts}",
        )
    )

    # ------------------------------------------------------------------
    # E8: no_duplicate_chunk_ids  [halt]
    # ------------------------------------------------------------------
    # chunk_id phải duy nhất trong tập cleaned — trùng chunk_id gây upsert
    # không nhất quán trên vector store (doc mới ghi đè doc khác).
    # metric_impact: phát hiện khi cleaning_rules sinh chunk_id trùng (hash collision
    #   hoặc seq bị reset sai); cleaned_records hợp lệ phải có 0 vi phạm.
    chunk_ids = [r.get("chunk_id", "") for r in cleaned_rows]
    seen_ids: set[str] = set()
    dup_ids: List[str] = []
    for cid in chunk_ids:
        if cid in seen_ids:
            dup_ids.append(cid)
        seen_ids.add(cid)
    ok8 = len(dup_ids) == 0
    results.append(
        ExpectationResult(
            "no_duplicate_chunk_ids",
            ok8,
            "halt",
            f"duplicate_chunk_ids={len(dup_ids)} examples={dup_ids[:3]}",
        )
    )

    # ------------------------------------------------------------------
    # E9: chunk_text_reasonable_length  [warn]
    # ------------------------------------------------------------------
    # chunk_text quá dài (> 2 000 ký tự) → embedding bị cắt ngầm, ảnh hưởng retrieval.
    # Chỉ warn (không halt) vì vẫn có thể publish; team cần xem lại chunking strategy.
    # metric_impact: số chunk vượt ngưỡng thường = 0 trên bộ sạch; tăng khi chunker
    #   gộp nhiều đoạn hoặc raw data có đoạn dài bất thường.
    MAX_CHUNK_LEN = 2_000
    too_long = [r for r in cleaned_rows if len(r.get("chunk_text") or "") > MAX_CHUNK_LEN]
    ok9 = len(too_long) == 0
    results.append(
        ExpectationResult(
            "chunk_text_reasonable_length",
            ok9,
            "warn",
            f"chunks_over_{MAX_CHUNK_LEN}_chars={len(too_long)}",
        )
    )

    halt = any(not r.passed and r.severity == "halt" for r in results)
    return results, halt


# ---------------------------------------------------------------------------
# Test thủ công  (python quality/expectations.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json

    load_dotenv(override=True)  # đảm bảo OPENAI_API_KEY có mặt khi chạy standalone

    # Dữ liệu mẫu tối thiểu — thay bằng cleaned CSV thực để kiểm tra đầy đủ
    sample: List[Dict[str, Any]] = [
        {
            "chunk_id": "policy_refund_v4_1_abc",
            "doc_id": "policy_refund_v4",
            "chunk_text": "Yêu cầu được gửi trong vòng 7 ngày làm việc kể từ thời điểm xác nhận đơn hàng.",
            "effective_date": "2026-02-01",
            "exported_at": "2026-04-10T08:00:00",
        },
        {
            "chunk_id": "sla_p1_2026_2_def",
            "doc_id": "sla_p1_2026",
            "chunk_text": "Ticket P1 có SLA phản hồi ban đầu 15 phút và resolution trong 4 giờ.",
            "effective_date": "2026-02-01",
            "exported_at": "2026-04-10T08:00:00",
        },
        {
            "chunk_id": "it_helpdesk_faq_3_ghi",
            "doc_id": "it_helpdesk_faq",
            "chunk_text": "Tài khoản bị khóa sau 5 lần đăng nhập sai liên tiếp.",
            "effective_date": "2026-02-01",
            "exported_at": "2026-04-10T08:00:00",
        },
        {
            "chunk_id": "hr_leave_policy_4_jkl",
            "doc_id": "hr_leave_policy",
            "chunk_text": "Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm theo chính sách 2026.",
            "effective_date": "2026-02-01",
            "exported_at": "2026-04-10T08:00:00",
        },
    ]

    results, should_halt = run_expectations(sample)
    print(f"\n{'='*60}")
    print(f"  Expectation Suite — {len(results)} checks | should_halt={should_halt}")
    print(f"{'='*60}")
    for r in results:
        status = "PASS" if r.passed else ("HALT" if r.severity == "halt" else "WARN")
        print(f"  [{status:4}] [{r.severity:4}] {r.name:<45} {r.detail}")
    print(f"{'='*60}\n")
