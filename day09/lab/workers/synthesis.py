"""
workers/synthesis.py — Synthesis Worker
Sprint 2: Tổng hợp câu trả lời từ retrieved_chunks và policy_result.

Input (từ AgentState):
    - task: câu hỏi
    - retrieved_chunks: evidence từ retrieval_worker
    - policy_result: kết quả từ policy_tool_worker

Output (vào AgentState):
    - final_answer: câu trả lời cuối với citation
    - sources: danh sách nguồn tài liệu được cite
    - confidence: mức độ tin cậy (0.0 - 1.0)

Gọi độc lập để test:
    python workers/synthesis.py
"""

import os

WORKER_NAME = "synthesis_worker"

SYSTEM_PROMPT = """Bạn là trợ lý IT Helpdesk nội bộ.

Quy tắc nghiêm ngặt:
1. CHỈ trả lời dựa vào context được cung cấp. KHÔNG dùng kiến thức ngoài.
2. Nếu context không đủ để trả lời → nói rõ "Không đủ thông tin trong tài liệu nội bộ".
3. Trích dẫn nguồn cuối mỗi câu quan trọng: [tên_file].
4. Trả lời súc tích, có cấu trúc. Không dài dòng.
5. Nếu có exceptions/ngoại lệ → nêu rõ ràng trước khi kết luận.
"""


def _call_llm(messages: list) -> str:
    """
    Gọi LLM để tổng hợp câu trả lời.
    Retry logic và validation để đảm bảo không bị placeholder.
    """
    def is_valid_answer(text: str) -> bool:
        """Validate answer không phải placeholder hoặc quá ngắn."""
        if not text or len(text.strip()) < 20:
            return False
        placeholders = ["[placeholder", "[template", "[example", "synthesize here", "your answer here"]
        return not any(p.lower() in text.lower() for p in placeholders)

    # Option A: OpenAI (ưu tiên)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        for attempt in range(2):  # Retry 1 lần nếu cần
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.1,  # Low temperature để grounded
                max_tokens=800,
            )
            answer = response.choices[0].message.content.strip()
            if is_valid_answer(answer):
                return answer
        
        # Nếu vẫn không valid → dùng Gemini
    except Exception as e:
        print(f"[SYNTHESIS] OpenAI failed: {e}")

    # Option B: Gemini (backup)
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        for attempt in range(2):  # Retry 1 lần
            combined = "\n".join([m["content"] for m in messages])
            response = model.generate_content(combined)
            answer = response.text.strip()
            if is_valid_answer(answer):
                return answer
    except Exception as e:
        print(f"[SYNTHESIS] Gemini failed: {e}")

    # Fallback cuối: trả về thông báo rõ ràng
    return "[SYNTHESIS ERROR] Không thể tạo câu trả lời. Vui lòng kiểm tra lại câu hỏi hoặc liên hệ IT support."


def _build_context(chunks: list, policy_result: dict) -> str:
    """Xây dựng context string từ chunks và policy result."""
    parts = []

    if chunks:
        parts.append("=== TÀI LIỆU THAM KHẢO ===")
        for i, chunk in enumerate(chunks, 1):
            source = chunk.get("source", "unknown")
            text = chunk.get("text", "")
            score = chunk.get("score", 0)
            parts.append(f"[{i}] Nguồn: {source} (relevance: {score:.2f})\n{text}")

    if policy_result and policy_result.get("exceptions_found"):
        parts.append("\n=== POLICY EXCEPTIONS ===")
        for ex in policy_result["exceptions_found"]:
            parts.append(f"- {ex.get('rule', '')}")

    if not parts:
        return "(Không có context)"

    return "\n\n".join(parts)


def _estimate_confidence(chunks: list, answer: str, policy_result: dict) -> float:
    """
    Ước tính confidence dựa vào:
    - Số lượng và quality của chunks
    - Có exceptions không
    - Answer có abstain không

    TODO Sprint 2: Có thể dùng LLM-as-Judge để tính confidence chính xác hơn.
    """
    if not chunks:
        return 0.1  # Không có evidence → low confidence

    if "Không đủ thông tin" in answer or "không có trong tài liệu" in answer.lower():
        return 0.3  # Abstain → moderate-low

    # Weighted average của chunk scores
    if chunks:
        avg_score = sum(c.get("score", 0) for c in chunks) / len(chunks)
    else:
        avg_score = 0

    # Penalty nếu có exceptions (phức tạp hơn)
    exception_penalty = 0.05 * len(policy_result.get("exceptions_found", []))

    confidence = min(0.95, avg_score - exception_penalty)
    return round(max(0.1, confidence), 2)


def synthesize(task: str, chunks: list, policy_result: dict) -> dict:
    """
    Tổng hợp câu trả lời từ chunks và policy context.

    Returns:
        {"answer": str, "sources": list, "confidence": float}
    """
    context = _build_context(chunks, policy_result)

    # Build messages
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"""Câu hỏi: {task}

{context}

Hãy trả lời câu hỏi dựa vào tài liệu trên."""
        }
    ]

    answer = _call_llm(messages)
    sources = list({c.get("source", "unknown") for c in chunks})
    confidence = _estimate_confidence(chunks, answer, policy_result)

    return {
        "answer": answer,
        "sources": sources,
        "confidence": confidence,
    }


def run(state: dict) -> dict:
    """
    Worker entry point — gọi từ graph.py.
    
    Contract compliance:
    - Input: task, retrieved_chunks, policy_result
    - Output: final_answer, sources, confidence
    - Logging: worker_io_logs với timestamp
    """
    task = state.get("task", "")
    chunks = state.get("retrieved_chunks", [])
    policy_result = state.get("policy_result", {})

    # Initialize state fields nếu chưa có
    state.setdefault("workers_called", [])
    state.setdefault("history", [])
    state.setdefault("worker_io_logs", [])
    
    state["workers_called"].append(WORKER_NAME)

    # Contract-compliant worker_io log
    worker_io = {
        "worker": WORKER_NAME,
        "input": {
            "task": task,
            "chunks_count": len(chunks),
            "has_policy": bool(policy_result),
            "policy_applies": policy_result.get("policy_applies") if policy_result else None,
        },
        "output": {},
        "error": None,
        "timestamp": __import__('datetime').datetime.now().isoformat(),
    }

    try:
        # Validate input cơ bản
        if not task.strip():
            raise ValueError("Task cannot be empty")
            
        # Gọi synthesize với validation
        result = synthesize(task, chunks, policy_result)
        
        # Validate output trước khi gán vào state
        if not result.get("answer") or len(result["answer"].strip()) < 10:
            raise ValueError("Generated answer too short or empty")
            
        if result["confidence"] < 0.1:
            raise ValueError("Confidence too low")

        # Gán kết quả vào state
        state["final_answer"] = result["answer"].strip()
        state["sources"] = result["sources"]
        state["confidence"] = result["confidence"]

        # Contract-compliant worker_io output
        worker_io["output"] = {
            "answer_length": len(result["answer"]),
            "sources": result["sources"],
            "confidence": result["confidence"],
            "has_citations": any(source in result["answer"] for source in result["sources"]),
        }
        
        state["history"].append(
            f"[{WORKER_NAME}] answer generated, confidence={result['confidence']:.2f}, "
            f"sources={len(result['sources'])}, length={len(result['answer'])}"
        )

    except Exception as e:
        # Contract-compliant error handling
        error_obj = {"code": "SYNTHESIS_FAILED", "reason": str(e)}
        worker_io["error"] = error_obj
        
        # Fallback answer khi lỗi
        state["final_answer"] = f"[SYNTHESIS ERROR] Không thể tạo câu trả lời: {str(e)}"
        state["sources"] = []
        state["confidence"] = 0.0
        state["history"].append(f"[{WORKER_NAME}] ERROR: {e}")

    state["worker_io_logs"].append(worker_io)
    return state


# ─────────────────────────────────────────────
# Test độc lập
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Synthesis Worker — Contract Compliance Test")
    print("=" * 60)

    test_cases = [
        {
            "name": "Basic SLA Query",
            "task": "SLA ticket P1 là bao lâu?",
            "retrieved_chunks": [
                {
                    "text": "Ticket P1: Phản hồi ban đầu 15 phút kể từ khi ticket được tạo. Xử lý và khắc phục 4 giờ.",
                    "source": "sla_p1_2026.txt",
                    "score": 0.92,
                }
            ],
            "policy_result": {},
            "expected_confidence_min": 0.7,
        },
        {
            "name": "Policy Exception Case",
            "task": "Khách hàng Flash Sale yêu cầu hoàn tiền vì lỗi nhà sản xuất.",
            "retrieved_chunks": [
                {
                    "text": "Ngoại lệ: Đơn hàng Flash Sale không được hoàn tiền theo Điều 3 chính sách v4.",
                    "source": "policy_refund_v4.txt",
                    "score": 0.88,
                }
            ],
            "policy_result": {
                "policy_applies": False,
                "exceptions_found": [{"type": "flash_sale_exception", "rule": "Flash Sale không được hoàn tiền."}],
            },
            "expected_confidence_min": 0.5,
        },
        {
            "name": "No Evidence Case",
            "task": "Cách reset password cho hệ thống XYZ?",
            "retrieved_chunks": [],
            "policy_result": {},
            "expected_answer_contains": "Không đủ thông tin",
        },
        {
            "name": "Multiple Sources Case",
            "task": "Quy trình escalation cho incident critical?",
            "retrieved_chunks": [
                {
                    "text": "Critical incident: Phải escalate trong vòng 15 phút.",
                    "source": "escalation_guide.txt",
                    "score": 0.95,
                },
                {
                    "text": "Incident level 1: Gọi điện trực tiếp cho on-call engineer.",
                    "source": "incident_handbook.txt",
                    "score": 0.85,
                }
            ],
            "policy_result": {},
            "expected_sources_count_min": 2,
        },
        {
            "name": "Empty Task Case",
            "task": "",
            "retrieved_chunks": [{"text": "Some content", "source": "test.txt", "score": 0.9}],
            "policy_result": {},
            "should_fail": True,
        },
    ]

    all_passed = True

    for tc in test_cases:
        print(f"\n[TEST] {tc['name']}")
        print(f"Task: {tc['task'][:60]}...")
        
        try:
            result = run({
                "task": tc["task"],
                "retrieved_chunks": tc["retrieved_chunks"],
                "policy_result": tc["policy_result"],
            })
            
            # Validate contract compliance
            required_fields = ["final_answer", "sources", "confidence"]
            for field in required_fields:
                if field not in result:
                    print(f"  ❌ FAIL: Missing field '{field}' in result")
                    all_passed = False
                    continue
            
            answer = result.get("final_answer", "")
            sources = result.get("sources", [])
            confidence = result.get("confidence", 0.0)
            
            print(f"  ✅ Answer length: {len(answer)}")
            print(f"  ✅ Sources: {len(sources)}")
            print(f"  ✅ Confidence: {confidence:.2f}")
            
            # Test-specific validations
            if "expected_confidence_min" in tc:
                if confidence < tc["expected_confidence_min"]:
                    print(f"  ❌ FAIL: Confidence too low (expected >={tc['expected_confidence_min']})")
                    all_passed = False
            
            if "expected_answer_contains" in tc:
                if tc["expected_answer_contains"] not in answer:
                    print(f"  ❌ FAIL: Answer doesn't contain expected text")
                    all_passed = False
            
            if "expected_sources_count_min" in tc:
                if len(sources) < tc["expected_sources_count_min"]:
                    print(f"  ❌ FAIL: Not enough sources")
                    all_passed = False
            
            if "should_fail" in tc and tc["should_fail"]:
                if "ERROR" not in answer:
                    print(f"  ❌ FAIL: Expected error but got success")
                    all_passed = False
                else:
                    print(f"  ✅ Correctly failed with error")
            
            # Validate worker_io_logs
            worker_logs = result.get("worker_io_logs", [])
            if worker_logs:
                last_log = worker_logs[-1]
                if last_log.get("worker") != WORKER_NAME:
                    print(f"  ❌ FAIL: worker_io_log missing or invalid")
                    all_passed = False
                else:
                    print(f"  ✅ worker_io_log format compliant")
            
        except Exception as e:
            print(f"  ❌ FAIL: Exception during test: {e}")
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ ALL TESTS PASSED — Contract compliance verified")
    else:
        print("❌ SOME TESTS FAILED — Check implementation")
    print("=" * 60)