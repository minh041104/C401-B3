# Single Agent vs Multi-Agent Comparison — Lab Day 09

**Nhóm:** ___________  
**Ngày:** 2026-04-14

> **Nguồn số liệu:**
> - Day 08: `day08/lab/results/scorecard_grading_variant_hybrid.md` và `day08/lab/logs/grading_run.json`
> - Day 09: `python eval_trace.py --analyze` và trace trong `artifacts/traces/`
> - Lưu ý: Bộ câu hỏi Day 08 và Day 09 không hoàn toàn giống nhau, nên các metric accuracy chỉ mang tính tham khảo nếu không cùng dataset.

---

## 1. Metrics Comparison

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) | Delta | Ghi chú |
|--------|----------------------|---------------------|-------|---------|
| Avg confidence | N/A | 0.426 | N/A | Day 08 không trace confidence |
| Avg latency (ms) | 3689 | 6845 | +3156 | Day 09 chậm hơn do supervisor + MCP/tool calls |
| Abstain rate (%) | 10% (1/10) | 6.7% (1/15) | -3.3 điểm % | Day 09 có abstain đúng ở q09 |
| Multi-hop accuracy | N/A | 0/2 case khó mở | N/A | Day 09 route đúng nhưng reasoning còn sai ở q13/q15 |
| Routing visibility | ✗ Không có | ✓ Có route_reason | N/A | Day 09 trace rõ từng bước |
| Debug time (estimate) | 15 phút | 5 phút | -10 phút | Trace giúp khoanh vùng nhanh worker gây lỗi |
| MCP usage rate | N/A | 40% (6/15) | N/A | Day 09 có external capability |

---

## 2. Phân tích theo loại câu hỏi

### 2.1 Câu hỏi đơn giản (single-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | Tốt trên các câu fact retrieval cơ bản | Tốt ở q01, q03, q04, q05, q08, q14 |
| Latency | Nhanh hơn | Chậm hơn |
| Observation | Một pipeline là đủ để trả lời fact đơn giản | Multi-agent không cải thiện rõ accuracy ở loại câu này, nhưng trace tốt hơn |

**Kết luận:** Multi-agent không cải thiện nhiều ở câu đơn giản. Chi phí latency tăng nhưng đổi lại trace và khả năng debug tốt hơn.

### 2.2 Câu hỏi multi-hop (cross-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | N/A trên cùng dataset | Chưa tốt ở q13 và q15 |
| Routing visible? | ✗ | ✓ |
| Observation | Khó biết sai ở retrieval hay reasoning | Day 09 route đúng sang `policy_tool_worker`, có MCP call, nhưng logic policy/synthesis vẫn sai |

**Kết luận:** Điểm mạnh của Day 09 nằm ở observability, không phải accuracy tức thời. Multi-agent giúp thấy rất rõ câu multi-hop bị hỏng ở worker nào, nhưng chưa tự động làm câu trả lời đúng hơn nếu logic worker còn yếu.

### 2.3 Câu hỏi cần abstain

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Abstain rate | 10% (1/10) | 6.7% (1/15) |
| Hallucination cases | Có rủi ro vì không có trace để kiểm tra | Vẫn còn rủi ro ở temporal/policy edge case như q12 |
| Observation | Single-agent khó chứng minh tại sao abstain | Day 09 cho thấy retrieval evidence yếu và answer ngắn với confidence thấp |

**Kết luận:** Day 09 abstain đúng ở q09, nhưng chưa đủ chặt ở các case policy temporal phức tạp.

---

## 3. Debuggability Analysis

### Day 08 — Debug workflow
```text
Khi answer sai -> phải đọc toàn bộ RAG pipeline code -> tìm lỗi ở indexing/retrieval/generation
Không có trace -> không biết bắt đầu từ đâu
Thời gian ước tính: 15 phút
```

### Day 09 — Debug workflow
```text
Khi answer sai -> đọc trace -> xem supervisor_route + route_reason
  -> Nếu route sai -> sửa supervisor routing logic
  -> Nếu retrieval sai -> test retrieval_worker độc lập
  -> Nếu synthesis sai -> test synthesis_worker độc lập
Thời gian ước tính: 5 phút
```

**Câu cụ thể nhóm đã debug:**

q15 cho thấy route đúng sang `policy_tool_worker`, có cả `search_kb` và `get_ticket_info`, nhưng answer cuối vẫn sai logic emergency access. Từ trace có thể kết luận lỗi nằm ở policy reasoning/synthesis chứ không phải supervisor routing.

---

## 4. Extensibility Analysis

| Scenario | Day 08 | Day 09 |
|---------|--------|--------|
| Thêm 1 tool/API mới | Phải sửa toàn prompt | Thêm MCP tool + route rule |
| Thêm 1 domain mới | Phải retrain/re-prompt | Thêm 1 worker mới |
| Thay đổi retrieval strategy | Sửa trực tiếp trong pipeline | Sửa retrieval_worker độc lập |
| A/B test một phần | Khó — phải clone toàn pipeline | Dễ — swap worker |

**Nhận xét:**

Day 09 linh hoạt hơn rõ ràng. `policy_tool_worker` đã gọi được `search_kb` và `get_ticket_info` mà không cần sửa core graph quá nhiều.

---

## 5. Cost & Latency Trade-off

| Scenario | Day 08 calls | Day 09 calls |
|---------|-------------|-------------|
| Simple query | 1 LLM call | 1 LLM call + supervisor/retrieval orchestration |
| Complex query | 1 LLM call | 1 synthesis LLM call + 1-2 MCP/tool calls |
| MCP tool call | N/A | 1-2 calls tùy câu |

**Nhận xét về cost-benefit:**

Day 09 tốn latency hơn nhưng đổi lại có trace, route visibility và khả năng mở rộng. Nếu mục tiêu chỉ là trả lời fact đơn giản, single-agent rẻ hơn. Nếu mục tiêu là vận hành hệ thống phức tạp và debug được, multi-agent đáng giá hơn.

---

## 6. Kết luận

> **Multi-agent tốt hơn single agent ở điểm nào?**

1. Có trace rõ ràng: route_reason, worker sequence, tool usage, latency.
2. Dễ debug và dễ mở rộng thêm tool/worker hơn hẳn single-agent.

> **Multi-agent kém hơn hoặc không khác biệt ở điểm nào?**

1. Chậm hơn đáng kể ở workload hiện tại và chưa tự động cải thiện accuracy ở câu khó.

> **Khi nào KHÔNG nên dùng multi-agent?**

Khi bài toán chủ yếu là fact lookup đơn giản, ít tool, ít workflow branching và ưu tiên latency/cost hơn observability.

> **Nếu tiếp tục phát triển hệ thống này, nhóm sẽ thêm gì?**

Thêm rule/prompt chặt hơn cho `policy_tool_worker` để xử lý đúng temporal policy (q12) và emergency access multi-hop (q13, q15), đồng thời bổ sung HITL khi confidence thấp nhưng task thuộc nhóm high-risk.
