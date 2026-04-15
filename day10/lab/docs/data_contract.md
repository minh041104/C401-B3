# Data Contract — Lab Day 10

Contract chính: `contracts/data_contract.yaml` version `1.0`.

Owner: **Monitoring + Data Contract Owner (Vinh)**. Dataset publish: `kb_chunk_export` vào collection `day10_kb`.

---

## 1. Nguồn dữ liệu (source map)

| Nguồn canonical | doc_id | Phương thức ingest | Failure mode chính | Metric / alert |
|---|---|---|---|---|
| `data/docs/policy_refund_v4.txt` (`policy/refund-v4.pdf`) | `policy_refund_v4` | Export CSV từ policy KB, clean thành chunk | Sync nhầm policy-v3 còn cửa sổ hoàn tiền 14 ngày; duplicate chunk text | `refund_no_stale_14d_window`, `duplicate_chunk_text`; halt nếu còn 14 ngày sau clean |
| `data/docs/sla_p1_2026.txt` (`support/sla-p1-2026.pdf`) | `sla_p1_2026` | Export CSV từ IT support KB | Thiếu chunk P1 hoặc doc_id sai làm retrieval không trả lời được SLA P1 | `each_critical_doc_has_min_chunks`; alert `#kb-pipeline-alerts` |
| `data/docs/it_helpdesk_faq.txt` (`support/helpdesk-faq.md`) | `it_helpdesk_faq` | Export CSV từ helpdesk FAQ | Timestamp export sai, nội dung malformed hoặc chunk quá dài | `exported_at_iso_or_quarantine`, `chunk_text_reasonable_length` |
| `data/docs/hr_leave_policy.txt` (`hr/leave-policy-2026.pdf`) | `hr_leave_policy` | Export CSV từ HR policy KB | Lẫn bản 2025 hoặc effective_date cũ hơn policy 2026 | `hr_leave_no_stale_10d_annual`, `hr_leave_min_effective_date` |

`data/docs/access_control_sop.txt` hiện là tài liệu tham khảo, chưa nằm trong `allowed_doc_ids`. Nếu nhóm muốn publish nguồn này, phải cập nhật đồng thời `transform/cleaning_rules.py`, `contracts/data_contract.yaml`, manifest/eval và tài liệu này.

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `chunk_id` | string | Có | ID ổn định sau clean, sinh từ `doc_id` + sequence + hash nội dung; dùng cho upsert/prune idempotent. |
| `doc_id` | string | Có | Phải thuộc `allowed_doc_ids`: `policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy`. |
| `chunk_text` | string | Có | Nội dung đã chuẩn hóa whitespace, min 8 ký tự; chunk quá 2.000 ký tự là WARN vì có nguy cơ embedding bị cắt. |
| `effective_date` | date | Có | Format `YYYY-MM-DD`; HR leave policy phải từ `2026-01-01` trở đi. |
| `exported_at` | datetime | Có | Format `YYYY-MM-DDTHH:MM:SS`; đây là watermark dữ liệu để tính `latest_exported_at` trong manifest. |

Manifest bắt buộc ghi `run_id`, `raw_records`, `cleaned_records`, `quarantine_records`, `latest_exported_at`, đường dẫn `cleaned_csv`, `quarantine_csv`, và trạng thái `freshness`.

---

## 3. Freshness SLA và alert

Freshness đo theo **data snapshot watermark**, không đo theo thời điểm chạy pipeline. Code đọc `manifest.latest_exported_at`; nếu manifest có nhúng cleaned summary thì có thể lấy max `exported_at` trong summary. `run_timestamp` chỉ dùng để debug.

Lệnh kiểm tra:

```bash
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run-id>.json
```

| Trạng thái | Điều kiện | Hành động |
|---|---|---|
| **PASS** | `age_hours <= 24` (`FRESHNESS_SLA_HOURS`) | Cho phép publish/report bình thường. |
| **WARN** | `24 < age_hours <= 48`, thiếu data timestamp, hoặc timestamp nằm tương lai do lệch clock | Chạy lại pipeline hoặc kiểm tra clock/export; ghi cảnh báo lên `#kb-pipeline-alerts`. |
| **FAIL** | Manifest mất/lỗi JSON, threshold config sai, hoặc `age_hours > 48` | Không dùng artifact này làm bằng chứng freshness; cần re-export dữ liệu và rerun pipeline. |

Với CSV mẫu của lab, `exported_at=2026-04-10T08:00:00` nên freshness có thể FAIL khi chạy sau SLA. Đây là kết quả hợp lý vì SLA áp cho tuổi của snapshot dữ liệu.

---

## 4. Quy tắc quarantine vs drop

Không drop im lặng ở bước cleaning. Record bị loại khỏi cleaned phải được ghi vào `artifacts/quarantine/quarantine_<run-id>.csv` với `reason`.

Các nhóm reason chính:

| Reason | Xử lý | Approver merge lại |
|---|---|---|
| `unknown_doc_id` | Quarantine; không publish vì chưa có canonical source trong contract | Data Contract Owner + owner nguồn |
| `missing_effective_date`, `invalid_effective_date_format`, `stale_hr_policy_effective_date` | Quarantine để sửa metadata/version | HR/Policy owner + Data Contract Owner |
| `missing_exported_at`, `invalid_exported_at`, `malformed_timeline_export_before_effective` | Quarantine vì ảnh hưởng freshness và lineage | Monitoring Owner |
| `missing_chunk_text`, `malformed_missing_chunk_id`, `malformed_chunk_contains_nul_byte` | Quarantine vì không tạo được chunk hợp lệ | Pipeline/Cleaning owner |
| `duplicate_chunk_text` | Ghi quarantine để audit; chỉ giữ một chunk canonical trong cleaned | Cleaning owner |

Drop chỉ xảy ra sau khi record đã có dấu vết: vector store prune các `chunk_id` cũ không còn trong cleaned hiện tại để publish idempotent. Nếu cần merge lại record từ quarantine, phải sửa raw/canonical source rồi chạy lại pipeline, không sửa trực tiếp cleaned CSV.

---

## 5. Phiên bản & canonical

Source of truth cho refund là `data/docs/policy_refund_v4.txt`, upstream `policy/refund-v4.pdf`, effective date `2026-02-01`. Cửa sổ hoàn tiền canonical hiện tại là **7 ngày làm việc**; nội dung 14 ngày từ policy-v3 bị sửa có marker `[cleaned: stale_refund_window]` hoặc bị chặn bởi expectation nếu còn sót.

Source of truth cho HR leave là `data/docs/hr_leave_policy.txt`, upstream `hr/leave-policy-2026.pdf`, effective date tối thiểu `2026-01-01`. Bản HR 2025 có `10 ngày phép năm` không được publish.

Khi thêm version hoặc nguồn mới, cần cập nhật cùng lúc:

1. `contracts/data_contract.yaml` (`canonical_sources`, `allowed_doc_ids`, versioning).
2. `transform/cleaning_rules.py` allowlist/rule liên quan.
3. Manifest/eval bằng một run mới để chứng minh freshness, quarantine và retrieval vẫn nhất quán.
