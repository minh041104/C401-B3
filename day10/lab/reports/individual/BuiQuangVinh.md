# Báo cáo cá nhân — Lab Day 10

**Họ và tên:** Bùi Quang Vinh  
**Vai trò:** Monitoring + Data Contract Owner  
**Độ dài:** ~450 từ

---

## 1. Phụ trách

Tôi phụ trách ba file: `monitoring/freshness_check.py`, `contracts/data_contract.yaml` và `docs/data_contract.md`. Phần việc chính là hoàn thiện logic freshness theo SLA, thống nhất ý nghĩa **PASS/WARN/FAIL**, đồng thời điền đầy đủ owner, SLA, source map và canonical source trong contract/documentation.

Trong `freshness_check.py`, tôi bổ sung cách đọc watermark dữ liệu từ `manifest.latest_exported_at`; nếu manifest có nhúng cleaned summary thì fallback sang max `exported_at`. `run_timestamp` chỉ giữ lại để debug, không dùng thay watermark dữ liệu. Trong `data_contract.yaml` và `data_contract.md`, tôi ghi rõ dataset `kb_chunk_export`, owner Vinh, SLA 24h, grace 48h, alert channel, allowlist doc_id và các nguồn canonical.

**Bằng chứng:** commit `2cf8438 update freshness monitoring and data contract docs` có sửa code trong `monitoring/freshness_check.py` cùng hai file contract/doc. Đây cũng là phần bàn giao cho Người 6 để viết tổng hợp: rule monitoring, trạng thái freshness và data contract.

---

## 2. Quyết định kỹ thuật

**Freshness đo theo data snapshot, không theo giờ chạy pipeline:** một manifest có thể được tạo hôm nay nhưng dữ liệu bên trong đã cũ. Vì vậy `latest_exported_at` là nguồn chính để tính `age_hours`. Nếu dùng `run_timestamp`, pipeline có thể báo xanh giả dù source export đã quá SLA.

**PASS/WARN/FAIL nhất quán với SLA:**  
- **PASS** khi `age_hours <= 24`, nghĩa là snapshot còn trong SLA.  
- **WARN** khi `24 < age_hours <= 48`, hoặc thiếu data timestamp/timestamp hơi lệch tương lai. Trạng thái này vẫn cho phép điều tra và rerun pipeline trong grace window.  
- **FAIL** khi manifest mất, JSON lỗi, config threshold sai, hoặc `age_hours > 48`. Khi đó artifact không nên dùng làm bằng chứng freshness.

**Contract là source of truth:** tôi đưa `canonical_sources`, `allowed_doc_ids`, `policy_versioning`, `freshness.status_policy` vào YAML để các owner khác có cùng một chuẩn khi cleaning, expectation, grading và report.

---

## 3. Sự cố / anomaly

Anomaly chính là sample lab có `latest_exported_at=2026-04-10T08:00:00` trong khi pipeline chạy ngày 15/04/2026. Nếu chỉ nhìn `run_timestamp`, artifact trông mới; nhưng tuổi snapshot thực tế vượt xa SLA 24h. Logic mới trả **FAIL** với reason `freshness_grace_window_exceeded`, phản ánh đúng rủi ro dữ liệu stale.

Tôi cũng xử lý các case không sạch của manifest: file mất, JSON invalid, manifest không phải object, timestamp parse lỗi, hoặc cấu hình `warn_after_hours < sla_hours`. Các lỗi này được trả về `detail` rõ ràng để runbook/summary không phải parse text log.

---

## 4. Before/after

**Before:** freshness chủ yếu kiểm tra đơn giản theo timestamp có sẵn; trạng thái chưa tách rõ grace window, và contract chưa mô tả đầy đủ owner/SLA/source map/canonical source.

**After:** manifest mới như `artifacts/manifests/manifest_2026-04-15T10-13Z.json` ghi:

```json
"freshness": {
  "status": "FAIL",
  "detail": {
    "latest_exported_at": "2026-04-10T08:00:00",
    "timestamp_field": "latest_exported_at",
    "age_hours": 122.234,
    "sla_hours": 24.0,
    "warn_after_hours": 48.0,
    "reason": "freshness_grace_window_exceeded"
  }
}
```

Contract/doc sau sửa đã có source map cho `policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy`; đồng thời mô tả rõ quarantine reason liên quan freshness như `missing_exported_at`, `invalid_exported_at`, `malformed_timeline_export_before_effective`.

---

## 5. Cải tiến thêm 2 giờ

Đọc `sla_hours`, `warn_after_hours` và `alert_channel` trực tiếp từ `contracts/data_contract.yaml` khi chạy `etl_pipeline.py freshness`, thay vì truyền mặc định trong Python. Thêm test nhỏ cho ba mốc thời gian: PASS ở 23h, WARN ở 25h, FAIL ở 49h để tránh lệch định nghĩa SLA khi nhóm tiếp tục chỉnh pipeline.
