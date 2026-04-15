# Báo cáo cá nhân — Day 10 Lab

**Họ và tên:** Nguyễn Bình Minh
**Vai trò:** Retrieval Eval Owner
**Độ dài:** ~450 từ

---

## 1. Phụ trách

Tôi triển khai `eval_retrieval.py` — script chấm retrieval before/after dùng
Chroma collection `day10_kb` do embed owner publish. Output là CSV có đủ cột
`contains_expected`, `hits_forbidden`, `top1_doc_expected` cho cả nhãn
`before` và `after`, cộng thêm `llm_verdict` / `llm_reason` khi bật
`--llm-judge`. Kết nối với pipeline owner qua artifact `artifacts/cleaned/*.csv`
(nguồn truth để embed) và manifest `latest_exported_at` (xác nhận eval đang
chạy trên đúng snapshot vừa publish).

**Bằng chứng:** `eval_retrieval.py`, `artifacts/eval/before.csv`,
`artifacts/eval/after.csv`, `artifacts/eval/after_judge.csv`, commit
`3ef5708 feat: eval`.

---

## 2. Quyết định kỹ thuật

**Keyword check trước, LLM judge sau:** tôi tách 2 lớp. Lớp 1 là check offline
(`contains_expected` / `hits_forbidden` / `top1_doc_expected`) — deterministic,
chạy trong CI không cần API key. Lớp 2 là LLM judge dùng
`response_format=json_object` và `temperature=0` để parse ổn định thành
`{verdict, reason}`. Lý do: keyword phát hiện leak (vd "14 ngày") rất nhanh,
còn judge bắt được trường hợp top-k lan man ngữ nghĩa mà keyword vẫn pass.

**Label-driven output:** mỗi run gắn `--label before|after` → cùng
fieldnames, dễ diff 2 CSV thay vì tách schema. Summary in ra stderr
(`contains_ok / forbidden_hit / top1_ok / judge_relevant`) để grep nhanh.

---

## 3. Sự cố / anomaly

Lần đầu chạy `--label after` sau khi pipeline `run --no-refund-fix`, cột
`hits_forbidden=yes` trên câu refund dù tôi tưởng đã embed lại. Nguyên nhân:
chưa prune vector id cũ trong collection → top-k vẫn trả chunk "14 ngày" từ
lần embed trước. Fix: phối hợp với embed owner bổ sung bước prune
(`prev_ids - ids`) trong `cmd_embed_internal`, và tôi chạy lại eval trên
manifest mới. Bài học: eval không tin được nếu index không phải snapshot
publish.

---

## 4. Before/after

**CSV:** `artifacts/eval/before.csv` câu `q_refund_window` có
`contains_expected=no`, `hits_forbidden=yes`; `artifacts/eval/after.csv` cùng
câu → `contains_expected=yes`, `hits_forbidden=no`, `top1_doc_expected=yes`.

**LLM judge:** `artifacts/eval/after_judge.csv` cho verdict `relevant` với
reason ngắn xác nhận top-k đã chứa cửa sổ 7 ngày; bản before cho `irrelevant`
vì lẫn stale content.

---

## 5. Cải tiến thêm 2 giờ

Đưa danh sách câu hỏi golden ra ngoài (`data/test_questions.json` theo schema
có `expect_top1_doc_id`) và thêm mode `--diff before.csv after.csv` in trực
tiếp bảng các câu regressed, để report nhóm không phải mở 2 CSV cạnh nhau.
