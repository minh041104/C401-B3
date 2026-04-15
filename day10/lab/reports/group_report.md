# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** C401-B3  
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| Trần Quốc Việt | Ingestion / Raw Owner | vquoc2532@gmail.com |
| Nguyễn Việt Hoàng | Cleaning & Quality Owner | hoangnvhe170385@fpt.edu.vn |
| Ngô Quang Phúc | Quality / Expectation Owner | phuc652003@gmail.com |
| Bùi Quang Vinh | Monitoring / Contract Owner | Noterday1@gmail.com |
| Nguyễn Bình Minh | Retrieval Eval Owner | minhnguyen041104@gmail.com |
| Lê Quang Minh | Grading / Final Evidence Owner | Mninh25@gmail.com|

**Ngày nộp:**15-04-2026
**Repo:** https://github.com/minh041104/C401-B3  
**Độ dài khuyến nghị:** 600–1000 từ

---

> **Nộp tại:** `reports/group_report.md`  
> **Deadline commit:** xem `SCORING.md` (code/trace sớm; report có thể muộn hơn nếu được phép).  
> Phải có **run_id**, **đường dẫn artifact**, và **bằng chứng before/after** (CSV eval hoặc screenshot).

---

## 1. Pipeline tổng quan (150–200 từ)

> Nguồn raw là gì (CSV mẫu / export thật)? Chuỗi lệnh chạy end-to-end? `run_id` lấy ở đâu trong log?

**Tóm tắt luồng:**
Pipeline xử lý dữ liệu policy từ file CSV `policy_export_dirty.csv` với 10 bản ghi ban đầu. Sau quá trình cleaning và validation, đầu ra có 6 bản ghi sạch và 4 bản ghi bị quarantine. Dữ liệu được embed vào ChromaDB collection `day10_kb` với model `all-MiniLM-L6-v2`. Run ID được sinh tự động dựa trên timestamp: `2026-04-15T10-13Z`.

**Lệnh chạy một dòng (copy từ README thực tế của nhóm):**
```bash
python etl_pipeline.py run
```

**Kết quả thực tế:**
- Raw records: 10
- Cleaned records: 6  
- Quarantine records: 4
- Freshness status: FAIL (122.2h > 24h SLA)
- Exit code: 0 (thành công)

---

## 2. Cleaning & expectation (150–200 từ)

> Baseline đã có nhiều rule (allowlist, ngày ISO, HR stale, refund, dedupe…). Nhóm thêm **≥3 rule mới** + **≥2 expectation mới**. Khai báo expectation nào **halt**.

### 2a. Bảng metric_impact (bắt buộc — chống trivial)

| Rule / Expectation mới (tên ngắn) | Trước (số liệu) | Sau / khi inject (số liệu) | Chứng cứ (log / CSV / commit) |
|-----------------------------------|------------------|-----------------------------|-------------------------------|
| refund_no_stale_14d_window | violations=0 | violations=0 | manifest_2026-04-15T10-13Z.json |
| hr_leave_no_stale_10d_annual | violations=0 | violations=0 | manifest_2026-04-15T10-13Z.json |
| each_critical_doc_has_min_chunks | missing_docs=[] | counts={'policy_refund_v4': 2, 'sla_p1_2026': 1, 'it_helpdesk_faq': 2, 'hr_leave_policy': 1} | manifest_2026-04-15T10-13Z.json |

**Rule chính (baseline + mở rộng):**

- **refund_no_stale_14d_window**: Đảm bảo policy refund không quá 14 ngày cũ
- **hr_leave_no_stale_10d_annual**: HR leave policy không quá 10 ngày cũ  
- **each_critical_doc_has_min_chunks**: Mỗi document quan trọng phải có ít nhất 1 chunk

**Ví dụ expectation hoạt động:**
Tất cả 9 expectation đều PASS (halt=0, warn=0). Không có expectation nào fail trong run này. Các expectation critical như `effective_date_iso_yyyy_mm_dd` và `no_duplicate_chunk_ids` đều đạt chuẩn.

---

## 3. Before / after ảnh hưởng retrieval hoặc agent (200–250 từ)

> Bắt buộc: inject corruption (Sprint 3) — mô tả + dẫn `artifacts/eval/…` hoặc log.

**Kịch bản inject:**
Sử dụng dữ liệu demo với freshness check FAIL (120h > 24h SLA). Dữ liệu được xử lý qua pipeline và đánh giá retrieval quality với 3 câu hỏi grading.

**Kết quả định lượng (từ grading_run.jsonl):**
- **gq_d10_01** (Policy refund): ✅ contains_expected=true, ❌ hits_forbidden=true
- **gq_d10_02** (SLA P1): ✅ contains_expected=true, ✅ hits_forbidden=false  
- **gq_d10_03** (HR leave): ✅ contains_expected=true, ✅ hits_forbidden=false, ✅ top1_doc_matches=true

**Phân tích:**
- 2/3 câu đạt yêu cầu (Pass/Merit level)
- Câu gq_d10_01 bị hits_forbidden do retrieval trả về document có chứa từ khóa không mong muốn
- Cần cải thiện filtering để loại bỏ forbidden terms

---

## 4. Freshness & monitoring (100–150 từ)

> SLA bạn chọn, ý nghĩa PASS/WARN/FAIL trên manifest mẫu.

**Freshness SLA được cấu hình:**
- **PASS**: age_hours ≤ 24 (dữ liệu mới trong vòng 24h)
- **WARN**: 24 < age_hours ≤ 48 (cảnh báo dữ liệu cũ)
- **FAIL**: age_hours > 48 (dữ liệu quá cũ)

**Kết quả thực tế:**
- Latest exported_at: 2026-04-10T08:00:00
- Age: 122.2 giờ
- **Status: FAIL** (vượt SLA 24h)
- Lý do: freshness_grace_window_exceeded

**Giải pháp:**
- Document như known issue trong risk matrix
- Cập nhật source data timestamp hoặc extend SLA cho demo environment
- Monitor freshness qua manifest để tracking SLA compliance

---

## 5. Liên hệ Day 09 (50–100 từ)

> Dữ liệu sau embed có phục vụ lại multi-agent Day 09 không? Nếu có, mô tả tích hợp; nếu không, giải thích vì sao tách collection.

**Tích hợp Day 09:**
- **Shared Collection**: `day10_kb` được sử dụng chung với Day 09 RAG system
- **Embedding Model**: `all-MiniLM-L6-v2` đồng bộ giữa các ngày
- **Chunk Strategy**: 512 tokens, overlap 50 - consistent

**Lợi ích:**
- Day 09 không cần re-index khi có policy mới
- Retrieval quality consistent qua các ngày
- Shared monitoring cho corpus freshness

**Integration Flow**: Day 10 Pipeline → day10_kb collection → Day 09 RAG retrieval → Agent responses

---

## 6. Rủi ro còn lại & việc chưa làm

**Rủi ro đã biết:**
1. **Stale policy data** (120h > 24h SLA) - Documented as known issue
2. **ChromaDB connection failure** - Retry logic (3x) implemented
3. **Schema drift** - Contract validation + versioning
4. **Large file processing** - Chunked processing enabled
5. **Duplicate policies** - Deduplication by doc_id

**Việc chưa làm:**
- Tích hợp Great Expectations cho advanced validation
- Freshness monitoring 2-boundary (ingest + publish)
- LLM-judge cho eval mở rộng
- Rule versioning tự động từ env/contract

**Cải tiến tương lai:**
- Auto-SLA adjustment dựa trên business requirements
- Real-time freshness alerts
- Advanced retrieval evaluation với LLM scoring