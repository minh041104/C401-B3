# Báo Cáo Cá Nhân — Lab Day 08: RAG Pipeline

**Họ và tên:** Ngô Quang Phúc

**Vai trò trong nhóm:** Eval Specialist

**Ngày nộp:** 2026-04-13

**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi đã làm gì trong lab này? (100-150 từ)

Trong lab này, tôi phụ trách vai trò Evaluation Specialist và làm việc chính ở Sprint 4. Phần tôi chịu trách nhiệm là xây dựng `eval.py`, gồm triển khai bốn hàm chấm điểm (scoring functions): `score_faithfulness`, `score_answer_relevance`, `score_context_recall`, và `score_completeness`. Cả bốn hàm đều áp dụng phương pháp **LLM-as-Judge**: gửi prompt có cấu trúc đến LLM (hỗ trợ cả OpenAI và Google Gemini) và parse kết quả JSON trả về. Ngoài ra, tôi cũng xây dựng `run_scorecard()` để chạy toàn bộ 10 câu hỏi qua pipeline và tổng hợp điểm, hàm `compare_ab()` để so sánh baseline vs variant theo từng metric, `generate_scorecard_summary()` để xuất báo cáo markdown, và `generate_grading_log()` để xuất log theo chuẩn nộp bài. Đây là lớp đánh giá chất lượng của toàn bộ pipeline RAG.

---

## 2. Điều tôi hiểu rõ hơn sau lab này (100-150 từ)

Sau lab này, tôi hiểu rõ hơn hai điểm quan trọng. Thứ nhất là **LLM-as-Judge là công cụ đánh giá mạnh nhưng cần prompt rõ ràng**. Ban đầu tôi nghĩ chỉ cần hỏi LLM "điểm bao nhiêu" là xong, nhưng thực tế tôi phải thiết kế thang điểm 1–5 cụ thể, mô tả từng mức, và yêu cầu output đúng định dạng JSON — nếu không, response sẽ không nhất quán và khó parse. Thứ hai là **bốn metrics đo bốn khía cạnh khác nhau của RAG**: Faithfulness đo generation quality (model có bịa không), Answer Relevance đo focus (có trả lời đúng câu hỏi không), Context Recall đo retrieval quality (đúng nguồn chưa), còn Completeness đo độ đầy đủ so với expected answer. Nhìn riêng từng metric mới thấy được lỗi nằm ở tầng nào trong pipeline.

---

## 3. Điều tôi ngạc nhiên hoặc gặp khó khăn (100-150 từ)

Điều tôi ngạc nhiên nhất là kết quả `Context Recall` đạt **5.00/5** ở baseline với toàn bộ 10 câu — kể cả các câu "hard" như q07 (alias query) và q10 (VIP refund). Điều đó cho thấy indexing và retrieval của nhóm đã rất tốt từ đầu. Khó khăn lớn hơn với tôi là xử lý **câu hỏi không có expected source** như q09 (`ERR-403-AUTH`). Hàm `score_context_recall` phải trả về `None` thay vì 0 để không làm sai average — vì đây không phải retrieval failure mà là bài toán "abstain" khi không có dữ liệu. Một thách thức khác là parse JSON từ LLM judge: đôi khi model trả về JSON nằm trong markdown code block hoặc kèm thêm text thừa, nên tôi phải dùng `raw.find("{")` và `raw.rfind("}")` để extract phần JSON thực sự. Bài học là luôn cần fallback khi làm việc với LLM output.

---

## 4. Phân tích một câu hỏi trong scorecard (150-200 từ)

**Câu hỏi q07:** "Approval Matrix để cấp quyền hệ thống là tài liệu nào?"

**Phân tích:**

Tôi chọn q07 vì đây là câu thể hiện rõ nhất sự tách biệt giữa tầng retrieval và tầng generation trong scorecard. Câu này được gắn nhãn `"hard"` với note "Đây là query alias/tên cũ — thử nghiệm hybrid retrieval", vì người dùng dùng tên cũ "Approval Matrix" thay vì tên mới "Access Control SOP". Ở baseline (`retrieval_mode = "dense"`), kết quả chấm cho thấy `Faithfulness = 5/5`, `Relevance = 5/5`, `Recall = 5/5`, nhưng `Completeness = 2/5`. Điều này cho thấy retriever dense đã tìm được đúng tài liệu `it/access-control-sop.md` (recall hoàn hảo), và model không bịa thêm thông tin (faithfulness cao), nhưng câu trả lời lại thiếu nhiều điểm quan trọng của expected answer — cụ thể là thông tin về việc tài liệu "Approval Matrix" chính là tên cũ của "Access Control SOP". Với tôi, lỗi completeness ở đây nằm ở bước generation: prompt chưa hướng dẫn model kết nối tên cũ–tên mới một cách tường minh. Đây là bằng chứng để nhóm ưu tiên cải thiện prompt template hơn là thay đổi chunking.

---

## 5. Nếu có thêm thời gian, tôi sẽ làm gì? (50-100 từ)

Nếu có thêm thời gian, tôi sẽ thử hai cải tiến cho phần evaluation. Thứ nhất, tôi sẽ thêm metric **Answer Length Ratio** — so sánh độ dài câu trả lời với expected answer, vì q07 và q10 cho thấy completeness thấp thường đi kèm với câu trả lời quá ngắn. Thứ hai, tôi sẽ chạy **multi-judge** bằng cách gọi judge LLM 3 lần và lấy median score để giảm variance, vì kết quả LLM-as-Judge đôi khi không ổn định giữa các lần gọi với cùng input. Hai cải tiến này bám sát các điểm yếu đã thấy trong scorecard thực tế.
