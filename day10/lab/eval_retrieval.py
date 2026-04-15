#!/usr/bin/env python3
"""
Đánh giá retrieval — before/after khi pipeline đổi dữ liệu embed.

Hai lớp kiểm tra:
1) Keyword check (mặc định, offline): contains_expected / hits_forbidden /
   top1_doc_expected trên top-k chunk từ Chroma.
2) LLM-judge (tuỳ chọn, bật bằng --llm-judge): dùng Claude để chấm ngữ nghĩa
   xem top-k có thực sự trả lời đúng câu hỏi hay không.

Ví dụ:
  python eval_retrieval.py --label before --out artifacts/eval/before.csv
  python eval_retrieval.py --label after  --out artifacts/eval/after.csv
  python eval_retrieval.py --label after  --llm-judge
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent

JUDGE_SYSTEM = (
    "Bạn là retrieval judge cho hệ thống RAG nội bộ. "
    "Với mỗi câu hỏi, bạn nhận top-k chunk đã retrieve và danh sách keyword kỳ vọng. "
    "Nhiệm vụ: đánh giá top-k có đủ thông tin để trả lời đúng không.\n\n"
    "Trả về DUY NHẤT một JSON object dạng:\n"
    '{"verdict": "relevant" | "partial" | "irrelevant", "reason": "<1 câu tiếng Việt, <= 160 ký tự>"}\n\n'
    "Quy tắc:\n"
    "- relevant: top-k chứa câu trả lời đúng, không mâu thuẫn với keyword kỳ vọng.\n"
    "- partial: có liên quan nhưng thiếu chi tiết then chốt hoặc lẫn thông tin stale.\n"
    "- irrelevant: không trả lời được hoặc chứa thông tin sai/cấm.\n"
    "Không thêm markdown, không thêm text ngoài JSON."
)


def _default_out(label: str) -> Path:
    if label:
        return ROOT / "artifacts" / "eval" / f"{label}.csv"
    return ROOT / "artifacts" / "eval" / "before_after_eval.csv"


def _build_judge_client() -> Tuple[Any, str] | Tuple[None, str]:
    """Khởi tạo OpenAI client nếu có SDK + API key. Trả về (client, model) hoặc (None, reason)."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None, "missing OPENAI_API_KEY"
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        return None, "openai SDK not installed (pip install openai)"
    model = os.environ.get("JUDGE_MODEL", "gpt-4o-mini")
    return OpenAI(api_key=api_key), model


def _judge_one(
    client: Any,
    model: str,
    question: str,
    docs: List[str],
    must_any: List[str],
    must_not: List[str],
) -> Tuple[str, str]:
    """Chấm một câu bằng LLM. Trả về (verdict, reason)."""
    joined = "\n\n".join(f"[chunk {i+1}]\n{d}" for i, d in enumerate(docs) if d) or "(không có chunk)"
    user_msg = (
        f"Câu hỏi: {question}\n\n"
        f"Keyword kỳ vọng (must_contain_any): {must_any or '(none)'}\n"
        f"Keyword cấm (must_not_contain): {must_not or '(none)'}\n\n"
        f"Top-k chunk retrieve được:\n{joined}"
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=200,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
        )
        text = (resp.choices[0].message.content or "").strip()
        data = json.loads(text)
        verdict = str(data.get("verdict", "")).lower().strip()
        reason = str(data.get("reason", "")).strip().replace("\n", " ")
        if verdict not in {"relevant", "partial", "irrelevant"}:
            verdict = "irrelevant"
        return verdict, reason[:200]
    except Exception as e:
        return "error", f"judge_error: {type(e).__name__}: {e}"[:200]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--questions",
        default=str(ROOT / "data" / "test_questions.json"),
        help="JSON danh sách câu hỏi golden (retrieval)",
    )
    parser.add_argument(
        "--out",
        default="",
        help="CSV kết quả (mặc định artifacts/eval/<label>.csv khi có --label)",
    )
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument(
        "--label",
        default="",
        help="Gắn nhãn run (vd: before, after) — ghi vào cột label của CSV",
    )
    parser.add_argument(
        "--llm-judge",
        action="store_true",
        help="Thêm cột llm_verdict/llm_reason bằng cách gọi Claude judge",
    )
    args = parser.parse_args()

    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        print("Install: pip install chromadb sentence-transformers", file=sys.stderr)
        return 1

    qpath = Path(args.questions)
    if not qpath.is_file():
        print(f"questions not found: {qpath}", file=sys.stderr)
        return 1

    questions = json.loads(qpath.read_text(encoding="utf-8"))
    db_path = os.environ.get("CHROMA_DB_PATH", str(ROOT / "chroma_db"))
    collection_name = os.environ.get("CHROMA_COLLECTION", "day10_kb")
    model_name = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    client = chromadb.PersistentClient(path=db_path)
    emb = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
    try:
        col = client.get_collection(name=collection_name, embedding_function=emb)
    except Exception as e:
        print(f"Collection error: {e}", file=sys.stderr)
        return 2

    out_path = Path(args.out) if args.out else _default_out(args.label)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    judge_client = None
    judge_model = ""
    if args.llm_judge:
        judge_client, info = _build_judge_client()
        if judge_client is None:
            print(f"WARN: --llm-judge disabled: {info}", file=sys.stderr)
        else:
            judge_model = info
            print(f"llm_judge enabled model={judge_model}", file=sys.stderr)

    fieldnames = [
        "label",
        "question_id",
        "question",
        "top1_doc_id",
        "top1_preview",
        "contains_expected",
        "hits_forbidden",
        "top1_doc_expected",
        "top_k_used",
        "llm_verdict",
        "llm_reason",
    ]
    summary: Dict[str, int] = {
        "total": 0,
        "contains_ok": 0,
        "forbidden_hit": 0,
        "top1_ok": 0,
        "judge_relevant": 0,
    }
    with out_path.open("w", encoding="utf-8", newline="") as fcsv:
        w = csv.DictWriter(fcsv, fieldnames=fieldnames)
        w.writeheader()
        for q in questions:
            text = q["question"]
            res = col.query(query_texts=[text], n_results=args.top_k)
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            top_doc = (metas[0] or {}).get("doc_id", "") if metas else ""
            preview = (docs[0] or "")[:180].replace("\n", " ") if docs else ""
            blob = " ".join(docs).lower()
            must_any = [x for x in q.get("must_contain_any", [])]
            forbidden = [x for x in q.get("must_not_contain", [])]
            ok_any = any(m.lower() in blob for m in must_any) if must_any else True
            bad_forb = any(m.lower() in blob for m in forbidden) if forbidden else False
            want_top1 = (q.get("expect_top1_doc_id") or "").strip()
            top1_expected = ""
            if want_top1:
                top1_expected = "yes" if top_doc == want_top1 else "no"

            llm_verdict = ""
            llm_reason = ""
            if judge_client is not None:
                llm_verdict, llm_reason = _judge_one(
                    judge_client, judge_model, text, list(docs), must_any, forbidden
                )

            summary["total"] += 1
            if ok_any:
                summary["contains_ok"] += 1
            if bad_forb:
                summary["forbidden_hit"] += 1
            if top1_expected == "yes":
                summary["top1_ok"] += 1
            if llm_verdict == "relevant":
                summary["judge_relevant"] += 1

            w.writerow(
                {
                    "label": args.label,
                    "question_id": q.get("id", ""),
                    "question": text,
                    "top1_doc_id": top_doc,
                    "top1_preview": preview,
                    "contains_expected": "yes" if ok_any else "no",
                    "hits_forbidden": "yes" if bad_forb else "no",
                    "top1_doc_expected": top1_expected,
                    "top_k_used": args.top_k,
                    "llm_verdict": llm_verdict,
                    "llm_reason": llm_reason,
                }
            )

    print(f"Wrote {out_path}")
    print(
        "summary "
        f"label={args.label or '-'} "
        f"total={summary['total']} "
        f"contains_ok={summary['contains_ok']} "
        f"forbidden_hit={summary['forbidden_hit']} "
        f"top1_ok={summary['top1_ok']} "
        f"judge_relevant={summary['judge_relevant']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
