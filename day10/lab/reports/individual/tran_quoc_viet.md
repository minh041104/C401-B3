# Báo cáo cá nhân

**Họ và tên:** Trần Quốc Việt
**Vai trò:** Ingestion / Pipeline Entrypoint Owner  
**Độ dài:** ~450 từ

---

## 1. Phụ trách

Tôi triển khai và ổn định luồng entrypoint pipeline trong `etl_pipeline.py`: `cmd_run`, `cmd_freshness`, `cmd_embed_internal`. Chịu trách nhiệm logging format theo rubric chấm, manifest structure đầy đủ, và cách README hướng dẫn lệnh chạy chuẩn định.

**Bằng chứng:** 
- Commit `etl_pipeline.py` có `_resolve_cli_path()`, `_slugify_run_id()`, `_write_manifest()` để chuẩn hóa path và log.
- [README.md](../README.md) phần "Chạy pipeline (Definition of Done tối thiểu)" nêu rõ lệnh chuẩn và artifact sinh ra.
- Artifact sau run: `artifacts/logs/run_*.log`, `artifacts/cleaned/cleaned_*.csv`, `artifacts/quarantine/quarantine_*.csv`, `artifacts/manifests/manifest_*.json`.

---

## 2. Quyết định kỹ thuật

**Path resolution độc lập cwd:**
Trước đây, script để `raw_path = Path(args.raw)` mà không xử lý đường dẫn tương đối → nếu gọi pipeline từ thư mục khác, raw file không tìm được. Sửa: `_resolve_cli_path()` luôn resolve sang tuyệt đối từ ROOT (`day10/lab/`). Đảm bảo robustness kể cả khi CI/automation chạy từ workspace root.

**Manifest structure cho manifest đầy đủ:**
Thay vì giữ lại manifest cũ (chỉ ghi `run_id`, `raw_records`, v.v.), tôi mở rộng manifest thêm:
- `artifacts`: lưu đầy đủ path của log, cleaned, quarantine, manifest.
- `validation`: ghi lại toàn bộ expectation results (name, passed, severity, detail).
- `embed`: status (attempted, status enum, collection, db_path).
- `freshness`: status, detail từ check, sla_hours.
- `exit_code`: rõ đối với downstream.

Điều này giúp truy xuất lỏng lẻo sau đó (quality_report, grading, runbook) mà không phải parse log text.

**Guard `--skip-validate` chỉ cho demo inject:**
Quy tắc: nếu dùng `--skip-validate` mà không có `--no-refund-fix` → reject ngay với `exit_code=1`. Lý do: `--skip-validate` được thiết kế cho kịch bản "inject hỏng, bỏ qua halt, cố embed xấu để chứng minh eval tệ" (Sprint 3). Dùng `--skip-validate` mà refund fix vẫn on là vô nghĩa → chặn sớm.

**Halt flow vẫn ghi manifest:**
Khi validation fail (halt), pipeline dừng trước embed (`exit_code=2`) nhưng vẫn ghi manifest đầy đủ + freshness check. Lý do: cleaning/quality owner cần manifest để quality_report mô tả tại sao halt; grading/GV cũng cần biết lý do fail.

---

## 3. Sự cố / anomaly

**Lần đầu pipeline hung khi embed chromadb:**
Sau khi apply refund fix và expectation pass, chạy embed đến đó hang. Nguyên nhân: model `all-MiniLM-L6-v2` lần đầu tải từ HF (~90MB), chạy mà không có timeout → trông như hang. Fix: bọc `cmd_embed_internal()` trong try-except; log ra lỗi nếu chromadb không install hoặc model fail.

**Path display khác platform:**
Manifest ghi path với `\\` (Windows backslash). Khi chuyển data sang Linux hoặc log, những con đường này lạc hậu. Fix: dùng `.as_posix()` khi display path trong manifest → luôn `/` dù trên Windows hay Linux.

---

## 4. Before/after

**Log chuẩn (after):**
```
run_id=copilot-verify
raw_records=10
cleaned_records=6
quarantine_records=4
cleaned_csv=artifacts/cleaned/cleaned_copilot-verify.csv
quarantine_csv=artifacts/quarantine/quarantine_copilot-verify.csv
expectation[min_one_row] OK (halt) :: cleaned_rows=6
expectation[refund_no_stale_14d_window] OK (halt) :: violations=0
…
embed_upsert count=6 collection=day10_kb
manifest_written=artifacts/manifests/manifest_copilot-verify.json
freshness_check=FAIL {"latest_exported_at": "2026-04-10T08:00:00", "age_hours": 115.982, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}
PIPELINE_OK
```

Đốc `run_id`, `raw_records`, `cleaned_records`, `quarantine_records`, expectation results — khớp rubric SCORING.md.

**Halt scenario validation (after):**
```
exit_code=2
pipeline_status=halted_validation
embed.status=skipped_validation_halt
manifest được ghi: artifacts/manifests/manifest_copilot-halt.json
```
Trước đó không ghi manifest khi halt → cleanup owner không có proof.

**Guard `--skip-validate` (after):**
```
$ python etl_pipeline.py run --skip-validate
ERROR: --skip-validate chỉ dành cho demo inject; hiện tại hãy dùng kèm --no-refund-fix.
exit_code=1
```
Trước đó `--skip-validate` không có guard → demo owner dễ gọi nhầm.

---

## 5. Cải tiến thêm 2 giờ (tuỳ chọn)

1. Đọc `FRESHNESS_SLA_HOURS` từ `contracts/data_contract.yaml` thay vì `.env` duy nhất — tách bạch policy data từ secret config.
2. Lấy thêm metric vào manifest: `embed.embedded_ids_count`, `embed.unique_doc_ids`, `embed.pruned_stale_ids` để truy xuất idempotency trực tiếp.
3. Thêm schema validation optional bằng pydantic (tuỳ cleaning owner có dùng GE hay không) — manifest tự validate từ code.
