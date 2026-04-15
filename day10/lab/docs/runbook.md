# Runbook — Lab Day 10 (Retrieval Incident)

Hướng dẫn xử lý sự cố khi agent trả lời sai do retrieval lấy phải chunk stale
hoặc cleaning rule không hoạt động. Mỗi mục dưới đây bám vào các artifact cụ
thể của pipeline Day 10 (`artifacts/logs`, `artifacts/manifests`,
`artifacts/quarantine`, `artifacts/eval`) để đội trực có thể chẩn đoán nhanh.

---

## 1. Symptom

Agent trả lời mâu thuẫn với policy hiện hành. Hai case kinh điển dùng làm
evidence cho nhóm:

- **q_refund_window** — User hỏi: "Khách hàng có bao nhiêu ngày để yêu cầu
  hoàn tiền?"
  - Đúng: "7 ngày làm việc" (policy_refund_v4, effective 2026).
  - Sai: "14 ngày làm việc" — dấu hiệu embed còn chunk stale `refund_v3`.
- **q_leave_version** — User hỏi: "Nhân viên dưới 3 năm kinh nghiệm được bao
  nhiêu ngày phép năm?"
  - Đúng: "12 ngày phép năm" (hr_leave_policy 2026).
  - Sai: "10 ngày phép năm" — dấu hiệu chunk HR bản cũ chưa bị quarantine.

Các dấu hiệu phụ trợ: câu trả lời đổi theo từng lần hỏi, log agent trích dẫn
`doc_id` không còn trong manifest mới nhất, hoặc user báo "thông tin khác với
email công ty mới gửi".

---

## 2. Detection

Ba nguồn tín hiệu chính trong pipeline:

1. **Freshness** (`monitoring/freshness_check.py`)
   - Đọc `latest_exported_at` trong manifest mới nhất so với
     `FRESHNESS_SLA_HOURS`.
   - PASS = trong SLA; WARN = vượt SLA dưới 2×; FAIL = vượt ≥ 2× SLA hoặc
     thiếu timestamp → đội trực phải vào điều tra.

2. **Expectations** (`quality/expectations.py`)
   - Fail severity `halt` → pipeline dừng trước khi embed; log ghi
     `PIPELINE_HALT`. Đây là nguồn cảnh báo mạnh nhất.
   - Fail severity `warn` → vẫn chạy tiếp nhưng cần review.

3. **Eval retrieval** (`eval_retrieval.py`)
   - `contains_expected=no` → top-k không có keyword kỳ vọng.
   - `hits_forbidden=yes` → top-k chứa chunk stale/cấm (vd "14 ngày làm việc").
   - `top1_doc_expected=no` → top-1 không phải doc được kỳ vọng
     (vd `hr_leave_policy`).
   - `llm_verdict` ∈ {partial, irrelevant} → Claude judge xác nhận top-k
     không đủ trả lời, hữu ích khi keyword check pass nhưng ngữ nghĩa sai.

Ngưỡng báo động: bất kỳ 1 trong {halt fail, `hits_forbidden=yes`,
`llm_verdict=irrelevant`} đều đủ để khởi động diagnosis.

---

## 3. Diagnosis

Mục tiêu: xác định (a) chunk stale đến từ đâu, (b) cleaning/expectation đã
bắt được chưa, (c) eval có xác nhận regression không.

| Bước | Lệnh | Kết quả mong đợi |
|------|------|------------------|
| 1 | Đọc `artifacts/logs/run_*.log` mới nhất | Xem có dòng `PIPELINE_HALT` hoặc expectation fail không |
| 2 | Mở manifest `artifacts/manifests/manifest_*.json` | Kiểm `raw_records`, `cleaned_records`, `quarantine_records`, `freshness.status` |
| 3 | Xem `artifacts/quarantine/quarantine_*.csv` | Xác nhận row stale đã bị tách khỏi cleaned set |
| 4 | Chạy eval "before" để chụp ảnh hiện trạng | Lưu làm evidence |
| 5 | Đối chiếu với eval "after" sau khi fix | Xác nhận regression đã đóng |

Lệnh chẩn đoán cụ thể:

```bash
# 1) Xem log run gần nhất
ls -t artifacts/logs/ | head -n 1

# 2) Đọc manifest mới nhất
ls -t artifacts/manifests/ | head -n 1

# 3) Kiểm quarantine
ls artifacts/quarantine/

# 4) Chụp evidence "before" (pipeline chưa fix — inject lỗi để so sánh)
python etl_pipeline.py run --no-refund-fix --skip-validate
python eval_retrieval.py --label before --out artifacts/eval/before.csv

# 5) Chụp evidence "after" (pipeline fix đầy đủ)
python etl_pipeline.py run
python eval_retrieval.py --label after --out artifacts/eval/after.csv

# 6) (Tuỳ chọn) Chấm ngữ nghĩa bằng LLM judge
export OPENAI_API_KEY=sk-...
python eval_retrieval.py --label after --llm-judge \
  --out artifacts/eval/after_judge.csv
```

Đọc CSV eval theo thứ tự cột: `label`, `question_id`, `contains_expected`,
`hits_forbidden`, `top1_doc_expected`, `llm_verdict`. Nếu cả 4 tín hiệu đều
xấu ở `before` và đều tốt ở `after`, đó là evidence đóng incident.

---

## 4. Mitigation

Khi đã xác định nguyên nhân, áp dụng theo thứ tự từ nhẹ đến nặng:

1. **Rerun pipeline (fix đầy đủ)** — đủ trong phần lớn trường hợp, vì
   cleaning rules sẽ quarantine lại chunk stale và embed upsert theo
   `chunk_id` (xem `etl_pipeline.py:cmd_embed_internal`).
   ```bash
   python etl_pipeline.py run
   ```

2. **Force re-embed (khi vector store đã pollute)** — xoá collection rồi
   chạy lại; pipeline đã prune id không còn trong cleaned run nên embed sẽ
   đồng bộ lại snapshot.
   ```bash
   rm -rf chroma_db
   python etl_pipeline.py run
   ```

3. **Quarantine thủ công** — nếu rule chưa bắt được chunk stale, thêm doc
   vào cleaning rule hoặc chuyển row sang `data/raw/_quarantine/` trước khi
   rerun. Ghi lại doc_id trong incident ticket.

4. **Banner degraded** — nếu chưa fix kịp, bật flag
   `data_stale=true` trong agent frontend để hiển thị cảnh báo cho user và
   tạm route câu hỏi nhạy cảm sang human agent.

5. **Rollback** — nếu bản mới pollute nặng, khôi phục `chroma_db` từ snapshot
   gần nhất còn lành và khoá pipeline cho tới khi root cause được sửa.

Sau mỗi bước phải rerun `eval_retrieval.py --label after` để xác nhận các cột
evidence đã xanh trước khi đóng incident.

---

## 5. Prevention

1. **Expectation phủ các keyword cấm** — mỗi lần thấy chunk stale mới, thêm
   expectation (severity `halt`) vào `quality/expectations.py`; đây là hàng
   rào rẻ nhất và chạy trước khi embed.
2. **Alert tự động** — cảnh báo khi `hits_forbidden=yes` hoặc
   `llm_verdict=irrelevant` xuất hiện trong eval CI; gắn owner từ
   `contracts/data_contract.yaml`.
3. **Freshness SLA** — giữ `FRESHNESS_SLA_HOURS` ≤ 24 cho policy docs; nếu
   WARN xuất hiện 2 run liên tiếp, coi như sắp thành incident.
4. **Version trong manifest** — luôn log `effective_date` và `run_id` theo
   từng chunk (đã làm); review diff manifest giữa hai run để phát hiện
   regression sớm.
5. **Eval gating** — trước khi publish collection mới, CI phải chạy
   `eval_retrieval.py --label after` và chặn nếu bất kỳ câu nào trong
   `test_questions.json` có `hits_forbidden=yes` hoặc `contains_expected=no`.
6. **Guardrail ở tầng agent (Day 11)** — LLM judge online cho câu trả lời
   trước khi gửi user, fallback human khi judge trả về `irrelevant`.

---

## Evidence files

- `artifacts/eval/before.csv` — trước khi fix (expect `hits_forbidden=yes`
  cho `q_refund_window`, `top1_doc_expected=no` cho `q_leave_version`).
- `artifacts/eval/after.csv` — sau khi fix (expect tất cả tín hiệu xanh,
  `q_p1_sla.contains_expected=yes` giữ nguyên như control).
- `artifacts/eval/after_judge.csv` — (tuỳ chọn) xác nhận ngữ nghĩa bằng LLM
  judge cho các câu đã pass keyword check.
- `artifacts/logs/run_*.log` + `artifacts/manifests/manifest_*.json` — trace
  đầy đủ run_id, counts, expectation result dùng cho post-mortem.
