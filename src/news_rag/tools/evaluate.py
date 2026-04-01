#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import importlib
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple

from ..config import DEFAULT_ACTIVE_CORPUS, DEFAULT_EVAL_ANSWERS_FILE, EVALUATION_OUTPUT_DIR, ensure_runtime_dirs, resolve_corpus_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="???????????????")
    parser.add_argument("--answers", default=str(DEFAULT_EVAL_ANSWERS_FILE), help="????????? txt/jsonl")
    parser.add_argument("--report-out", default=str(EVALUATION_OUTPUT_DIR / "evaluation_report.json"), help="???????")
    parser.add_argument("--details-out", default=str(EVALUATION_OUTPUT_DIR / "evaluation_details.jsonl"), help="????????")
    parser.add_argument("--corpus", default=DEFAULT_ACTIVE_CORPUS, help="??????? full ? first100")
    parser.add_argument("--data-file", help="???? jsonl ?????????? --corpus")
    parser.add_argument("--embedding-file", help="embedding ?????????? --corpus")
    parser.add_argument("--top-k", type=int, default=50, help="????")
    parser.add_argument("--top-n", type=int, default=5, help="???????")
    parser.add_argument("--max-query-rounds", type=int, default=3, help="??????")
    parser.add_argument("--mode", default="Combine", choices=["Combine", "True", "False"], help="????")
    parser.add_argument("--limit", type=int, default=0, help="???? N ?")
    parser.add_argument("--test10", action="store_true", help="???? 10 ???")
    return parser.parse_args()


def load_answers(path: Path) -> List[Dict[str, object]]:
    if path.suffix.lower() == ".txt":
        return load_answers_from_txt(path)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_answers_from_txt(path: Path) -> List[Dict[str, object]]:
    items: List[Dict[str, object]] = []
    blocks = [block for block in path.read_text(encoding="utf-8").strip().split("\n\n") if block.strip()]
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        items.append(
            {
                "id": len(items) + 1,
                "question": lines[0].split("问题:", 1)[1].strip(),
                "answer": lines[1].split("答案:", 1)[1].strip(),
                "source": json.loads(lines[2].split("出处JSON:", 1)[1].strip()),
            }
        )
    return items


def serialize_doc(doc: Dict[str, object]) -> Dict[str, object]:
    return {
        "doc_id": doc.get("doc_id"),
        "chunk_id": doc.get("chunk_id"),
        "chunk_total": doc.get("chunk_total"),
        "prompt": doc.get("prompt", ""),
        "completion": doc.get("completion", ""),
    }


def serialize_result(result: Dict[str, object], show_context: bool, show_docs: bool) -> Dict[str, object]:
    data = {
        "query": result["query"],
        "rewritten_queries": result["rewritten_queries"],
        "query_rounds": [
            {
                "round": item["round"],
                "queries": item["queries"],
                "assessment": {
                    "sufficient": item["assessment"].sufficient,
                    "reason": item["assessment"].reason,
                    "refinement_queries": item["assessment"].refinement_queries,
                },
            }
            for item in result["query_rounds"]
        ],
        "assessment": {
            "sufficient": result["assessment"].sufficient,
            "reason": result["assessment"].reason,
            "refinement_queries": result["assessment"].refinement_queries,
        },
        "final_queries": result["final_queries"],
        "answer": result["answer"],
    }
    if show_context:
        data["context"] = result["context"]
    if show_docs:
        data["docs"] = [serialize_doc(doc) for doc in result["docs"]]
    return data


def build_agent(args: argparse.Namespace):
    agent_module = importlib.import_module("news_rag.agent")
    default_data_file, default_embedding_file = resolve_corpus_paths(args.corpus)
    return agent_module.NewsRAGAgent(
        jsonl_file=args.data_file or default_data_file,
        embedding_path=args.embedding_file or default_embedding_file,
        corpus=args.corpus,
        top_k=args.top_k,
        top_n=args.top_n,
        retrieval_mode=args.mode,
        max_query_rounds=args.max_query_rounds,
    )


def run_queries(agent, questions: List[str]) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = []
    total = len(questions)
    for index, question in enumerate(questions, start=1):
        print(f"[{index}/{total}] 开始: {question}", flush=True)
        start_time = time.time()
        results.append(serialize_result(agent.answer(question), False, True))
        print(f"[{index}/{total}] 完成，用时 {time.time() - start_time:.1f}s", flush=True)
    return results


def compute_metrics(results: List[Dict[str, object]], gold_items: List[Dict[str, object]]) -> Tuple[Dict[str, object], List[Dict[str, object]]]:
    details: List[Dict[str, object]] = []
    total = min(len(results), len(gold_items))
    if total == 0:
        raise RuntimeError("没有可评测的数据")

    model_true_count = 0
    doc_hit_count = 0
    chunk_hit_count = 0
    top1_doc_hit_count = 0
    top1_chunk_hit_count = 0

    for index in range(total):
        gold = gold_items[index]
        result = results[index]
        docs = result.get("docs") or []
        source = gold.get("source") or {}
        gold_doc_id = source.get("doc_id")
        gold_chunk_id = source.get("chunk_id")
        model_judged_correct = bool((result.get("assessment") or {}).get("sufficient", False))
        doc_hit = any(doc.get("doc_id") == gold_doc_id for doc in docs)
        chunk_hit = any(doc.get("doc_id") == gold_doc_id and doc.get("chunk_id") == gold_chunk_id for doc in docs)
        first_doc = docs[0] if docs else {}
        top1_doc_hit = first_doc.get("doc_id") == gold_doc_id
        top1_chunk_hit = first_doc.get("doc_id") == gold_doc_id and first_doc.get("chunk_id") == gold_chunk_id

        model_true_count += int(model_judged_correct)
        doc_hit_count += int(doc_hit)
        chunk_hit_count += int(chunk_hit)
        top1_doc_hit_count += int(top1_doc_hit)
        top1_chunk_hit_count += int(top1_chunk_hit)

        details.append(
            {
                "id": gold.get("id", index + 1),
                "question": gold.get("question"),
                "gold_answer": gold.get("answer"),
                "predicted_answer": result.get("answer"),
                "model_judged_correct": model_judged_correct,
                "gold_source": source,
                "doc_hit": doc_hit,
                "chunk_hit": chunk_hit,
                "top1_doc_hit": top1_doc_hit,
                "top1_chunk_hit": top1_chunk_hit,
                "predicted_docs": [
                    {
                        "doc_id": doc.get("doc_id"),
                        "chunk_id": doc.get("chunk_id"),
                        "title": doc.get("prompt", "").splitlines()[0] if doc.get("prompt") else "",
                    }
                    for doc in docs
                ],
                "query_rounds": result.get("query_rounds", []),
            }
        )

    report = {
        "total": total,
        "model_true_rate": round(model_true_count / total, 4),
        "doc_hit_rate_at_top_n": round(doc_hit_count / total, 4),
        "chunk_hit_rate_at_top_n": round(chunk_hit_count / total, 4),
        "top1_doc_hit_rate": round(top1_doc_hit_count / total, 4),
        "top1_chunk_hit_rate": round(top1_chunk_hit_count / total, 4),
        "counts": {
            "model_true": model_true_count,
            "doc_hit_at_top_n": doc_hit_count,
            "chunk_hit_at_top_n": chunk_hit_count,
            "top1_doc_hit": top1_doc_hit_count,
            "top1_chunk_hit": top1_chunk_hit_count,
        },
    }
    return report, details


def write_details(path: Path, details: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in details) + "\n", encoding="utf-8")


def run_evaluation_cli() -> None:
    ensure_runtime_dirs()
    args = parse_args()
    answers_path = Path(args.answers)
    report_path = Path(args.report_out)
    details_path = Path(args.details_out)

    if not answers_path.exists():
        raise FileNotFoundError(f"找不到答案文件: {answers_path}")

    gold_items = load_answers(answers_path)
    if not gold_items:
        raise RuntimeError(f"答案文件为空或解析失败: {answers_path}")

    questions = [str(item.get("question", "")).strip() for item in gold_items]
    if any(not question for question in questions):
        raise RuntimeError("answers 文件中存在空问题，无法执行评测")

    effective_limit = 10 if args.test10 else args.limit
    if effective_limit > 0:
        questions = questions[:effective_limit]
        gold_items = gold_items[:effective_limit]

    print(
        f"开始评测，共 {len(questions)} 题。 mode={args.mode}, top_k={args.top_k}, top_n={args.top_n}, max_query_rounds={args.max_query_rounds}",
        flush=True,
    )
    print("正在初始化检索与问答组件，这一步可能较慢...", flush=True)
    init_start = time.time()
    agent = build_agent(args)
    print(f"初始化完成，用时 {time.time() - init_start:.1f}s", flush=True)

    results = run_queries(agent, questions)
    report, details = compute_metrics(results, gold_items)
    report["config"] = {
        "answers": str(answers_path),
        "top_k": args.top_k,
        "top_n": args.top_n,
        "max_query_rounds": args.max_query_rounds,
        "mode": args.mode,
        "test10": args.test10,
        "limit": effective_limit,
    }
    report["artifacts"] = {"details_out": str(details_path.resolve()), "report_out": str(report_path.resolve())}

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_details(details_path, details)

    print(f"评测完成，报告已写入: {report_path.resolve()}", flush=True)
    print(f"逐题结果已写入: {details_path.resolve()}", flush=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_evaluation_cli()
