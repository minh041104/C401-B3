# Báo cáo cá nhân — Lab Day 10: Data Pipeline & Data Observability

**Họ và tên:** Quang Minh  
**Vai trò:** Grading / Final Evidence Owner  
**Độ dài:** ~450 từ  

---

## 1. Phụ trách

Tôi triển khai `grading_run.py` và `instructor_quick_check.py` để đánh giá retrieval quality với 3 câu hỏi grading (gq_d10_01-03). Chịu trách nhiệm generate `grading_run.jsonl` và validate output với required IDs.

**Bằng chứng:**
- `artifacts/eval/grading_run.jsonl` - 3 entries với kết quả retrieval
- `artifacts/eval/grading_questions.json` - Input questions với criteria
- `instructor_quick_check.py` - Validation script cho JSONL structure

---

## 2. Quyết định kỹ thuật

**Grading criteria:** Implement 3-level validation (contains_expected, hits_forbidden, top1_doc_matches) để đảm bảo retrieval quality. Sử dụng top_k=5 để balance precision vs recall.

**Error handling:** Add retry logic (3x) cho ChromaDB connection và validate JSON structure trước khi write output. Log chi tiết từng câu hỏi để debug dễ dàng.

**File path:** Update default --questions path sang `artifacts/eval/grading_questions.json` để align với lab structure.

---

## 3. Sự cố / anomaly

**Issue:** `gq_d10_01` có `hits_forbidden=true` mặc dù contains_expected=true. Nguyên nhân: retrieval trả về document chứa "14 ngày" - từ khóa forbidden theo criteria.

**Root cause:** Vector similarity vẫn match document cũ có mention "14 ngày làm việc" trong context refund policy.

**Fix:** Cần improve filtering logic để loại bỏ documents có forbidden terms, hoặc cập nhật embedding strategy để reduce false positives.

---

## 4. Before/after

**Kết quả grading:**
- **gq_d10_01**: ❌ hits_forbidden=true (vấn đề filtering)
- **gq_d10_02**: ✅ all criteria pass
- **gq_d10_03**: ✅ all criteria pass + top1_doc_matches=true

**Metric impact:**
- Pass rate: 2/3 (66.7%) - đạt Merit level
- Retrieval precision: Cần cải thiện filtering để đạt Distinction

**Evidence:**
```json
{"id": "gq_d10_01", "hits_forbidden": true, "contains_expected": true, "status": "success"}
{"id": "gq_d10_02", "hits_forbidden": false, "contains_expected": true, "status": "success"}
{"id": "gq_d10_03", "hits_forbidden": false, "contains_expected": true, "top1_doc_matches": true, "status": "success"}
```

---

## 5. Cải tiến thêm 2 giờ

**Filtering enhancement:** Implement semantic filtering để detect và loại bỏ documents có ý nghĩa "policy cũ" hoặc "không còn hiệu lực".

**LLM-based evaluation:** Thêm LLM judge để evaluate retrieval quality với reasoning, không chỉ dựa vào keyword matching.

**Multi-language support:** Extend grading criteria để support Vietnamese policy documents với proper tokenization.

**Performance optimization:** Cache ChromaDB queries cho repeated questions để reduce latency trong batch evaluation.

**Integration:** Connect grading results với monitoring dashboard để track retrieval quality trends over time.