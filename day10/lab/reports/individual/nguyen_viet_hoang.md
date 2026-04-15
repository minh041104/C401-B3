# Báo cáo cá nhân — Nguyễn Việt Hoàng

**Họ và tên:** Nguyễn Việt Hoàng  
**Vai trò:** Cleaning Owner  
**Phạm vi phụ trách:** `transform/cleaning_rules.py`

---

## 1) Phần việc được giao

Trong Lab Day10, tôi phụ trách toàn bộ bước **clean** và **quarantine** theo Sprint 2, với ràng buộc chỉ sửa đúng file `transform/cleaning_rules.py`.  
Tôi **không chỉnh sửa** các phần ngoài phạm vi như `etl_pipeline.py`, `quality/expectations.py` hay tài liệu.

Mục tiêu tôi bám sát:
- Bổ sung tối thiểu 3 cleaning rule mới, có tác động đo được.
- Giữ rõ ràng luồng phân tách giữa `cleaned` và `quarantine`.
- Không thay đổi interface các hàm chính (`clean_rows`, `write_cleaned_csv`, `write_quarantine_csv`) để tránh ảnh hưởng các phần của thành viên khác.

Các rule baseline vẫn được bảo toàn:
- allowlist `doc_id`
- chuẩn hoá `effective_date`
- quarantine dữ liệu HR stale
- loại dòng rỗng (`chunk_text`/`effective_date`)
- dedupe
- fix refund window `14 -> 7`

---

## 2) Quyết định kỹ thuật và rule mới đã thêm

Tôi khai báo rõ các rule mới qua `NEW_RULE_IDS` để dễ đối chiếu rubric và viết báo cáo metric impact:

1. `unicode_whitespace_hygiene`  
   - Chuẩn hoá Unicode về NFC.  
   - Loại bỏ ký tự ẩn (zero-width/BOM).  
   - Chuẩn hoá các khoảng trắng Unicode về space chuẩn và gom khoảng trắng.  
   - **Tác động đo được:** có thể thay đổi `chunk_text`, từ đó thay đổi `chunk_id` và ảnh hưởng dedupe/downstream retrieval.

2. `exported_at_iso_or_quarantine`  
   - Parse/canonical `exported_at` về định dạng `YYYY-MM-DDTHH:MM:SS`.  
   - Quarantine nếu thiếu hoặc sai định dạng (`missing_exported_at`, `invalid_exported_at`).  
   - **Tác động đo được:** tăng `quarantine_records` khi timestamp lỗi, đồng thời chuẩn hoá dữ liệu thời gian cho downstream.

3. `malformed_row_guards`  
   - Chặn các bản ghi malformed: thiếu `chunk_id`, hoặc `chunk_text` chứa NUL byte (`\x00`).  
   - **Tác động đo được:** loại các dòng export hỏng cấu trúc trước khi đi vào cleaned.

4. `dedupe_doc_scoped_content`  
   - Dedupe theo khóa mạnh hơn `(doc_id, normalized_text)` thay vì chỉ theo text toàn cục.  
   - **Tác động đo được:** tránh gộp nhầm giữa hai tài liệu khác nhau nhưng có câu chữ giống nhau.

Ngoài các rule trên, tôi bổ sung kiểm tra timeline:
- `exported_at` không được trước `effective_date`.  
- Nếu vi phạm, đưa vào quarantine với reason `malformed_timeline_export_before_effective`.

---

## 3) Kết quả chạy và bằng chứng

Khi chạy pipeline chuẩn bằng lệnh `python etl_pipeline.py run`, manifest `artifacts/manifests/manifest_2026-04-15T04-40Z.json` ghi nhận:

- `raw_records = 10`
- `cleaned_records = 6`
- `quarantine_records = 4`
- `pipeline_status = ok`
- `exit_code = 0`

Bộ expectation hiện tại vẫn pass, đặc biệt các điều kiện quan trọng:
- `refund_no_stale_14d_window` = pass
- `effective_date_iso_yyyy_mm_dd` = pass

Điều này cho thấy phần cleaning mới không phá baseline và vẫn giữ pipeline chạy ổn định.

---

## 4) Bàn giao cho Người 3 và Người 5

**Bàn giao cho Người 3 (Quality/Expectations):**
- Dữ liệu cleaned đã canonical `effective_date` và `exported_at`.
- Quarantine có `reason` rõ ràng để viết expectation `halt/warn` theo mức độ nghiêm trọng.
- Không đổi interface nên phần expectation có thể tái sử dụng ngay.

**Bàn giao cho Người 5 (Retrieval/Eval):**
- Schema cleaned ổn định: `chunk_id`, `doc_id`, `chunk_text`, `effective_date`, `exported_at`.
- Dữ liệu sau clean đồng nhất hơn, hỗ trợ đánh giá before/after retrieval dễ truy vết.

---

## 5) Tự đánh giá mức độ hoàn thành

So với yêu cầu Người 2:
- [x] Có từ 3 rule mới trở lên (thực tế: 4 rule).
- [x] Rule có tên rõ, có mô tả và metric impact.
- [x] Giữ nguyên interface hàm chính.
- [x] Không sửa chéo file ngoài phạm vi.
- [x] Đầu ra cleaned/quarantine ổn định để nhóm tiếp tục expectation + eval.

---

## 6) Hướng cải tiến nếu có thêm thời gian

- Đưa thêm một số ngưỡng/rule sang config hoặc contract để giảm hard-code trong Python.
- Bổ sung test case tự động cho từng rule mới (unicode, malformed, exported_at, dedupe theo doc) để định lượng metric impact rõ hơn trên bộ dữ liệu inject.
