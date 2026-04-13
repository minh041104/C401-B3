# Báo Cáo Cá Nhân — Lab Day 08: RAG Pipeline

**Họ và tên:** Nguyễn Bình Minh  
**Vai trò trong nhóm:** Data Engineer  
**Ngày nộp:** 2026-04-13  
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi đã làm gì trong lab này? (100-150 từ)

Trong lab này, tôi phụ trách vai trò Data Engineer và làm việc chính ở Sprint 1. Phần tôi chịu trách nhiệm là xây dựng `index.py`, gồm đọc tài liệu từ `data/docs/`, tiền xử lý header, tách metadata như `source`, `department`, `effective_date`, `access`, sau đó chunk tài liệu theo section và ranh giới tự nhiên trước khi đẩy vào ChromaDB. Tôi chọn hướng chunking theo heading `=== ... ===` kết hợp fallback theo paragraph/câu để giữ ngữ nghĩa tốt hơn khi retrieve. Tôi cũng hỗ trợ Sprint 2 bằng cách kiểm tra xem các chunk đã giữ đủ metadata để team RAG gắn citation ổn định hay chưa. Đây là phần nền của cả pipeline.

---

## 2. Điều tôi hiểu rõ hơn sau lab này (100-150 từ)

Sau lab này, tôi hiểu rõ hơn hai điểm. Thứ nhất là chunking không chỉ là “cắt nhỏ văn bản”, mà là quyết định kiến trúc ảnh hưởng trực tiếp tới chất lượng trả lời. Nếu chunk quá lớn, retriever dễ lấy về nhiều ý gần nhau làm model chọn nhầm; nếu chunk quá nhỏ, câu trả lời lại thiếu ngữ cảnh. Thứ hai là metadata thực sự quan trọng trong RAG. Trước đây tôi nghĩ metadata chủ yếu để hiển thị nguồn, nhưng khi làm lab tôi thấy nó còn giúp kiểm soát freshness, phân biệt version và hỗ trợ citation. Với `source`, `section` và `effective_date`, nhóm có thể kiểm tra xem hệ thống đang lấy đúng tài liệu mới hay không.

---

## 3. Điều tôi ngạc nhiên hoặc gặp khó khăn (100-150 từ)

Điều làm tôi ngạc nhiên nhất là nhiều lỗi ban đầu trông giống lỗi indexing, nhưng khi nhìn vào scorecard thì không hẳn vậy. Tôi từng giả thuyết rằng nếu câu trả lời sai, nguyên nhân chủ yếu là chunking cắt dở hoặc metadata thiếu. Tuy nhiên, kết quả thực tế cho thấy `Context Recall` đạt 5.00/5 ở cả baseline và variant, và tuning log cũng ghi nhận số chunk thiếu `effective_date` là 0. Điều đó nghĩa là index của nhóm nhìn chung đã đủ tốt để lấy đúng nguồn mong đợi. Khó khăn lớn hơn nằm ở chỗ cùng một tài liệu có nhiều chi tiết gần nhau, khiến model dễ trộn nhầm khi tổng hợp. Bài học tôi rút ra là Data Engineer không chỉ build index cho “chạy được”, mà còn phải thiết kế index để giảm nhiễu ở bước generate.

---

## 4. Phân tích một câu hỏi trong scorecard (150-200 từ)

**Câu hỏi:** Contractor từ bên ngoài công ty có thể được cấp quyền Admin Access không? Nếu có, cần bao nhiêu ngày và có yêu cầu đặc biệt gì?

**Phân tích:**

Tôi chọn `gq05` vì đây là câu thể hiện rõ ranh giới giữa lỗi indexing và lỗi generation. Ở baseline, câu trả lời bị chấm `Faithfulness = 1/5`, dù `Context Recall = 5/5`. Nghĩa là retriever đã lấy đúng tài liệu `it/access-control-sop.md`, nhưng model chưa tổng hợp đúng các ý chính của `Level 4 — Admin Access`, đặc biệt là approver `IT Manager + CISO`, thời gian xử lý `5 ngày làm việc`, và training bắt buộc về security policy. Sang variant hybrid, faithfulness tăng lên `4/5`, nhưng completeness lại giảm xuống `2/5` vì model vẫn bỏ sót nhiều ý quan trọng. Với góc nhìn của tôi, lỗi chính ở đây không phải do indexing thất bại, vì nguồn đúng đã được retrieve ở cả hai bản. Tuy vậy, câu này cũng cho thấy index còn chỗ để cải thiện: nếu có thêm metadata như `access_level=Level 4` hoặc chunk tách gọn hơn, bước generate có thể bớt nhầm lẫn hơn.

---

## 5. Nếu có thêm thời gian, tôi sẽ làm gì? (50-100 từ)

Nếu có thêm thời gian, tôi sẽ thử hai cải tiến cho phần index. Thứ nhất, tôi sẽ bổ sung metadata cấu trúc hơn như `access_level`, `doc_type` hoặc `topic` để hỗ trợ retrieval chính xác hơn ở các câu nhiều chi tiết như `gq05`. Thứ hai, tôi sẽ thử tách nhỏ hơn ở các section có nhiều level, vì kết quả eval cho thấy model dễ trộn thông tin khi nhiều mức quyền nằm gần nhau trong cùng tài liệu. Hai thay đổi này bám sát lỗi thật của scorecard.
