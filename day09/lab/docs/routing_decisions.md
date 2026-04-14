# Routing Decisions Log — Lab Day 09

**Nhóm:** ___________  
**Ngày:** 2026-04-14

> **Nguồn dữ liệu:** Các entry dưới đây được lấy trực tiếp từ `artifacts/traces/` sau khi chạy `python eval_trace.py`.

---

## Routing Decision #1

**Task đầu vào:**
> SLA xử lý ticket P1 là bao lâu?

**Worker được chọn:** `retrieval_worker`  
**Route reason (từ trace):** `knowledge-base retrieval via ['sla', 'ticket', 'p1'] | risk_high=True from ['p1']`  
**MCP tools được gọi:** Không có  
**Workers called sequence:** `['retrieval_worker', 'synthesis_worker']`

**Kết quả thực tế:**
- final_answer (ngắn): Trả lời đúng các mốc chính: first response 15 phút, resolution 4 giờ, escalation sau 10 phút.
- confidence: `0.49`
- Correct routing? Yes

**Nhận xét:**

Routing này đúng. Supervisor nhận diện đây là câu hỏi truy vấn fact từ KB và không cần tool ngoài. Trace rõ ràng, dễ thấy câu này chỉ cần retrieval + synthesis.

---

## Routing Decision #2

**Task đầu vào:**
> Ai phải phê duyệt để cấp quyền Level 3?

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `access-control routing via ['cap quyen', 'phe duyet', 'level 3']`  
**MCP tools được gọi:** `search_kb`  
**Workers called sequence:** `['policy_tool_worker', 'synthesis_worker']`

**Kết quả thực tế:**
- final_answer (ngắn): Line Manager + IT Admin + IT Security.
- confidence: `0.41`
- Correct routing? Yes

**Nhận xét:**

Đây là ví dụ tốt cho routing theo domain. Câu hỏi chứa tín hiệu access control nên supervisor đẩy sang policy/tool worker thay vì retrieval thường. MCP `search_kb` cũng được gọi đúng để lấy evidence từ SOP.

---

## Routing Decision #3

**Task đầu vào:**
> Ticket P1 lúc 2am. Cần cấp Level 2 access tạm thời cho contractor để thực hiện emergency fix. Đồng thời cần notify stakeholders theo SLA. Nêu đủ cả hai quy trình.

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `access-control routing via ['access', 'level 2', 'contractor', 'tam thoi'] | policy route overrides retrieval signals ['sla', 'ticket', 'p1', 'notify'] | cross-domain query detected | risk_high=True from ['emergency', '2am', 'p1']`  
**MCP tools được gọi:** `search_kb`, `get_ticket_info`  
**Workers called sequence:** `['policy_tool_worker', 'synthesis_worker']`

**Kết quả thực tế:**
- final_answer (ngắn): Trả lời được cả phần access tạm thời và notify stakeholders theo SLA.
- confidence: `0.59`
- Correct routing? Partly

**Nhận xét:**

Supervisor route đúng vì đây là câu cross-domain, cần cả policy lẫn SLA và cần tool call. Tuy nhiên answer cuối vẫn chưa khớp hoàn toàn expected behavior của Level 2 emergency access. Nói cách khác: routing đúng, nhưng policy reasoning/synthesis phía sau còn lỗi. Đây là ví dụ trace giúp tách rõ “route đúng nhưng worker logic chưa đúng”.

---

## Routing Decision #4 (tuỳ chọn — bonus)

**Task đầu vào:**
> ERR-403-AUTH là lỗi gì và cách xử lý?

**Worker được chọn:** `retrieval_worker`  
**Route reason (từ trace):** `fallback to retrieval_worker for generic KB lookup | error code detected -> retrieve evidence first, escalate to HITL only if evidence remains weak | risk_high=True from ['error_code_or_cross_domain']`  
**MCP tools được gọi:** Không có  
**Workers called sequence:** `['retrieval_worker', 'synthesis_worker']`

**Kết quả thực tế:**
- final_answer (ngắn): `Không đủ thông tin trong tài liệu nội bộ.`
- confidence: `0.30`
- Correct routing? Yes

**Nhận xét:**

Đây là case abstain tốt. Hệ thống không bịa nghĩa của mã lỗi và trace cho thấy supervisor chủ động lấy evidence trước khi kết luận không đủ thông tin.

---

## Tổng kết

### Routing Distribution

| Worker | Số câu được route | % tổng |
|--------|------------------|--------|
| retrieval_worker | 9 | 60% |
| policy_tool_worker | 6 | 40% |
| human_review | 0 | 0% |

### Routing Accuracy

- Câu route đúng: 14 / 15
- Câu route đúng nhưng downstream logic còn sai: q15
- Câu trigger HITL: 0

### Lesson Learned về Routing

1. Rule-based routing bằng keyword/domain signal đủ tốt cho lab nhỏ và dễ trace hơn LLM router.
2. Route đúng chưa đủ; cần tách riêng lỗi supervisor và lỗi worker để debug chính xác.

### Route Reason Quality

`route_reason` hiện tại đủ tốt để debug nhanh vì có cả keyword match và risk signal. Nếu cải tiến thêm, nhóm nên chuẩn hóa format thành các trường riêng như `domain_signal`, `risk_signal`, `override_reason`, `needs_tool` để machine-readable hơn.
