import argparse
import json
from pathlib import Path

from ..config import DATA_CACHE_DIR, DATA_PROCESSED_DIR, DEFAULT_DATA_JSONL_FILE, ensure_runtime_dirs
from ..retrieval import EmbeddingRetriever, load_articles, select_first_n_docs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="为前 N 篇新闻对应的全部 chunk 构建测试用 embedding")
    parser.add_argument("--input", default=str(DEFAULT_DATA_JSONL_FILE), help="输入 jsonl 文件")
    parser.add_argument("--doc-limit", type=int, default=100, help="取前 N 篇新闻")
    parser.add_argument("--subset-jsonl", help="输出子集 jsonl 文件，默认写到 data/processed/data_firstN.jsonl")
    parser.add_argument("--output", help="输出 embedding 文件，默认写到 data/cache/embeddings_firstN.npy")
    return parser


def default_subset_jsonl(doc_limit: int) -> Path:
    return DATA_PROCESSED_DIR / f"data_first{doc_limit}.jsonl"


def default_embedding_output(doc_limit: int) -> Path:
    return DATA_CACHE_DIR / f"embeddings_first{doc_limit}.npy"


def save_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    ensure_runtime_dirs()
    args = build_parser().parse_args()

    if args.doc_limit <= 0:
        raise SystemExit("--doc-limit 必须大于 0")

    input_path = Path(args.input)
    subset_jsonl_path = Path(args.subset_jsonl) if args.subset_jsonl else default_subset_jsonl(args.doc_limit)
    output_path = Path(args.output) if args.output else default_embedding_output(args.doc_limit)

    articles = load_articles(input_path)
    subset_articles = select_first_n_docs(articles, args.doc_limit)
    if not subset_articles:
        raise SystemExit("没有选出任何 chunk，请检查输入文件或 doc-limit")

    save_jsonl(subset_articles, subset_jsonl_path)

    print(f"Selected {len(subset_articles)} chunks from the first {args.doc_limit} documents.")
    print(f"Subset jsonl: {subset_jsonl_path}")

    retriever = EmbeddingRetriever()
    embeddings = retriever.build_embeddings(subset_articles)
    retriever.save_embeddings(embeddings, output_path)

    print(f"Embedding shape: {embeddings.shape}")
    print(f"Embedding output: {output_path}")


if __name__ == "__main__":
    main()
