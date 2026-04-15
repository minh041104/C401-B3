# Báo cáo cá nhân — Day 10 Lab

**Họ và tên:** Ngô Quang Phúc  
**Vai trò:** Quality / Expectations Owner  
**Độ dài:** ~450 từ

---

## 1. Phụ trách

Tôi phụ trách `quality/expectations.py` — bộ expectation suite kiểm tra tập
cleaned trước khi embed lên vector store — và điền nội dung
`docs/quality_report_template.md` với số liệu thực từ pipeline.

Baseline đã có E1–E6. Tôi bổ sung ba expectation mới:

- **E7 `each_critical_doc_has_min_chunks`** (halt): đảm bảo mỗi doc quan trọng
  (`policy_refund_v4`, `sla_p1_2026`, `hr_leave_policy`, `it_helpdesk_faq`) còn
  ít nhất 1 chunk sau clean — phát hiện trường hợp toàn bộ chunk của 1 doc bị
  quarantine, khiến vector store không có gì để retrieve.
- **E8 `no_duplicate_chunk_ids`** (halt): `chunk_id` phải duy nhất trong tập
  cleaned — trùng id gây upsert không nhất quán, doc mới ghi đè doc khác.
- **E9 `chunk_text_reasonable_length`** (warn): chunk > 2 000 ký tự → embedding
  model MiniLM cắt ngầm, ảnh hưởng retrieval chất lượng.

Kết nối với pipeline owner: `run_expectations` nhận `cleaned_rows` từ
`etl_pipeline.py` sau bước clean; kết quả `should_halt` quyết định pipeline có
tiếp tục embed hay dừng.

**Bằng chứng:** `quality/expectations.py` (E7–E9), `docs/quality_report_template.md`
đã điền số liệu thực (`run_id=sprint2-clean`, `inject-bad`),
`artifacts/eval/before.csv`, `artifacts/eval/after.csv`,
`artifacts/eval/after_judge.csv` (do Người 5 cung cấp).

---

## 2. Quyết định kỹ thuật

**Halt vs warn — E7 và E8 là halt, E9 là warn:** E7 và E8 gây hỏng trực tiếp
vector store — thiếu doc hoặc trùng chunk_id đều làm retrieval trả sai ngay.
Ngược lại E9 chỉ làm giảm chất lượng embedding chứ không phá vỡ tính đúng đắn,
nên warn để pipeline vẫn publish nhưng team theo dõi.

**Tách metric_impact rõ ràng:** mỗi expectation mới có docstring mô tả chính xác
kịch bản inject nào kích hoạt nó và `quarantine_records` / `cleaned_records`
thay đổi thế nào — không phải expectation "trang trí" mà mỗi cái bắt được lỗi
cụ thể đo được.

**`load_dotenv(override=True)` ở cấp module:** đảm bảo khi `expectations.py`
được import bởi `etl_pipeline.py` lẫn khi chạy độc lập (`__main__`) đều nạp
đúng `.env` — tránh thiếu `OPENAI_API_KEY` khi LLM judge được bật downstream.

---

## 3. Sự cố / anomaly

Khi chạy `python quality/expectations.py` lần đầu với sample 4 dòng, E7 báo
`missing_docs=['it_helpdesk_faq', 'sla_p1_2026']` vì sample ban đầu tôi chỉ
thêm 2 doc. Fix: bổ sung đủ 4 doc trong sample `__main__`. Bài học: E7 rất nhạy
— bất kỳ doc nào thiếu trong tập cleaned đều bị bắt ngay, đúng mục đích thiết kế.

Lúc kiểm tra `inject-bad`, E3 (`refund_no_stale_14d_window`) FAIL với
`violations=1` — xác nhận chunk "14 ngày" còn trong cleaned khi bỏ `--no-refund-fix`.
Pipeline bypass được nhờ `--skip-validate` nhưng để lại bằng chứng rõ trong log.

---

## 4. Before/after

**Expectation log — pipeline chuẩn (`sprint2-clean`):**
```
expectation[each_critical_doc_has_min_chunks] OK (halt) :: missing_docs=[]; counts={'policy_refund_v4': 2, 'sla_p1_2026': 1, 'it_helpdesk_faq': 2, 'hr_leave_policy': 1}
expectation[no_duplicate_chunk_ids] OK (halt) :: duplicate_chunk_ids=0 examples=[]
expectation[chunk_text_reasonable_length] OK (warn) :: chunks_over_2000_chars=0
```

**Inject (`inject-bad` — `--no-refund-fix --skip-validate`):**
```
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
WARN: expectation failed but --skip-validate → tiếp tục embed (chỉ dùng cho demo Sprint 3).
```

**Retrieval eval (từ Người 5):** `before.csv` → `q_refund_window`:
`hits_forbidden=yes`; `after.csv` → `hits_forbidden=no`. `after_judge.csv` →
`q_leave_version`: `llm_verdict=relevant`, xác nhận 12 ngày phép 2026 đúng.

---

## 5. Cải tiến thêm 2 giờ

Đọc danh sách `CRITICAL_DOC_IDS` (dùng trong E7) từ `contracts/data_contract.yaml`
thay vì hard-code trong Python — khi nhóm thêm doc mới chỉ cần cập nhật contract,
không cần sửa code expectation. Thêm mode `--strict` cho `run_expectations` để
treat warn như halt trong môi trường CI production.
