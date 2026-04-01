import argparse
import json
import time
from pathlib import Path
from typing import List

from .config import DEFAULT_ACTIVE_CORPUS, DEFAULT_DATA_JSONL_FILE, ensure_runtime_dirs, resolve_corpus_paths


DEFAULT_QUERIES = [
    "杭州亚运会男子100米冠军是谁",
    "全国政协副主席、全国工商联主席是谁",
    "2024年3月8日习近平在湖南考察期间第一站来到哪所学校",
    "2024年中国红十字会成立多少周年",
]


def serialize_doc(doc: dict) -> dict:
    return {
        "doc_id": doc.get("doc_id"),
        "chunk_id": doc.get("chunk_id"),
        "chunk_total": doc.get("chunk_total"),
        "prompt": doc.get("prompt", ""),
        "completion": doc.get("completion", ""),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RAG + Agent 中文新闻问答入口")
    parser.add_argument("--query", help="单条问题")
    parser.add_argument("--query-file", help="批量问题文件，每行一条")
    parser.add_argument("--corpus", default=DEFAULT_ACTIVE_CORPUS, help="语料配置，例如 full 或 first100")
    parser.add_argument("--data-file", help="检索语料 jsonl 文件，显式指定时覆盖 --corpus")
    parser.add_argument("--embedding-file", help="embedding 文件，显式指定时覆盖 --corpus")
    parser.add_argument("--top-k", type=int, default=50, help="每轮召回数量")
    parser.add_argument("--top-n", type=int, default=5, help="每轮重排后保留数量")
    parser.add_argument("--max-query-rounds", type=int, default=3, help="最大查询轮次，包含首轮查询")
    parser.add_argument("--mode", default="Combine", choices=["Combine", "True", "False"], help="检索模式")
    parser.add_argument("--show-context", action="store_true", help="输出整理后的证据上下文")
    parser.add_argument("--show-docs", action="store_true", help="输出最终轮次的召回文档")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    return parser


def load_queries(args: argparse.Namespace) -> List[str]:
    if args.query:
        return [args.query.strip()]
    if args.query_file:
        with Path(args.query_file).open("r", encoding="utf-8") as file:
            return [line.strip() for line in file if line.strip()]
    return DEFAULT_QUERIES


def serialize_result(result: dict, show_context: bool, show_docs: bool) -> dict:
    data = {
        "query": result["query"],
        "query_time_ms": result.get("query_time_ms"),
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


def print_result(result: dict, show_context: bool, show_docs: bool) -> None:
    print(f"问题: {result['query']}")
    if result.get("query_time_ms") is not None:
        print(f"查询时间: {result['query_time_ms']} ms")
    print("第二轮改写候选: " + " | ".join(result["rewritten_queries"]))
    for item in result["query_rounds"]:
        print(f"查询轮次 {item['round']}: " + " | ".join(item["queries"]))
        print(
            "轮次检查: "
            f"sufficient={item['assessment'].sufficient}, "
            f"reason={item['assessment'].reason}"
        )
    print(f"答案: {result['answer']}")

    if show_context:
        print("\n整理后的上下文:")
        print(result["context"])

    if show_docs:
        print("\n最终轮次召回文档:")
        for index, doc in enumerate(result["docs"], start=1):
            print(f"[{index}] doc_id={doc.get('doc_id')} chunk_id={doc.get('chunk_id')}")
            print(doc.get("prompt", "").strip())
            completion = doc.get("completion", "").strip()
            print(completion[:300] + ("..." if len(completion) > 300 else ""))


def main() -> None:
    ensure_runtime_dirs()
    parser = build_parser()
    args = parser.parse_args()
    queries = load_queries(args)
    from .agent import NewsRAGAgent
    default_data_file, default_embedding_file = resolve_corpus_paths(args.corpus)

    agent = NewsRAGAgent(
        jsonl_file=args.data_file or default_data_file or DEFAULT_DATA_JSONL_FILE,
        embedding_path=args.embedding_file or default_embedding_file,
        corpus=args.corpus,
        top_k=args.top_k,
        top_n=args.top_n,
        retrieval_mode=args.mode,
        max_query_rounds=args.max_query_rounds,
    )

    for index, query in enumerate(queries):
        start = time.perf_counter()
        result = agent.answer(query)
        result["query_time_ms"] = int((time.perf_counter() - start) * 1000)
        if args.json:
            print(json.dumps(serialize_result(result, args.show_context, args.show_docs), ensure_ascii=False, indent=2))
        else:
            if index > 0:
                print("\n" + "=" * 80)
            print_result(result, args.show_context, args.show_docs)
