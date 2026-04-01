import json
from pathlib import Path
from typing import Iterable, List

import jieba
import numpy as np
import torch
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from .config import DEFAULT_EMBEDDINGS_FILE


def load_articles(jsonl_file: str | Path) -> List[dict]:
    articles: List[dict] = []
    with Path(jsonl_file).open("r", encoding="utf-8") as file:
        for line in file:
            try:
                articles.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return articles


def select_first_n_docs(articles: Iterable[dict], doc_limit: int) -> List[dict]:
    if doc_limit <= 0:
        return []

    selected: List[dict] = []
    doc_ids = set()
    for article in articles:
        doc_id = int(article.get("doc_id") or 0)
        if doc_id not in doc_ids:
            if len(doc_ids) >= doc_limit:
                break
            doc_ids.add(doc_id)
        selected.append(article)
    return selected


def build_bm25(articles: Iterable[dict]):
    corpus = [list(jieba.cut(article["completion"])) for article in articles]
    bm25 = BM25Okapi(corpus)
    return bm25, corpus


def bm25_search(query, bm25, articles, top_k=50):
    tokenized_query = list(jieba.cut(query))
    scores = bm25.get_scores(tokenized_query)
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [articles[index] for index in top_indices]


class EmbeddingRetriever:
    def __init__(self, model_name="BAAI/bge-large-zh", device="cpu"):
        self.device = device
        self.model = SentenceTransformer(model_name, device=device)

    def build_embeddings(self, articles):
        texts = [article["completion"] for article in articles]
        return self.model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=True,
        )

    def save_embeddings(self, embeddings, path: str | Path = DEFAULT_EMBEDDINGS_FILE):
        np.save(Path(path), embeddings)
        print(f"Embeddings saved to {Path(path)}")

    def load_embeddings(self, path: str | Path = DEFAULT_EMBEDDINGS_FILE):
        embeddings = np.load(Path(path))
        print(f"Embeddings loaded from {Path(path)}")
        return embeddings

    def search(self, query, embeddings, articles, top_k=50):
        query_vec = self.model.encode([query], normalize_embeddings=True)
        scores = np.dot(embeddings, query_vec.T).squeeze()
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [articles[index] for index in top_indices]


class Reranker:
    def __init__(self, model_name="BAAI/bge-reranker-base", device="cpu"):
        self.device = device
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.to(device)
        self.model.eval()

    def rerank(self, query, candidates, top_n=5):
        pairs = [[query, candidate["completion"]] for candidate in candidates]
        inputs = self.tokenizer(
            pairs,
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=512,
        )
        inputs = {key: value.to(self.device) for key, value in inputs.items()}

        with torch.no_grad():
            scores = self.model(**inputs).logits.squeeze(-1)

        sorted_indices = np.argsort(scores.cpu().numpy())[::-1][:top_n]
        return [candidates[index] for index in sorted_indices]


class TwoStageRetriever:
    def __init__(self, jsonl_file: str | Path, embedding_path: str | Path = DEFAULT_EMBEDDINGS_FILE):
        self.jsonl_file = Path(jsonl_file)
        self.embedding_path = Path(embedding_path)

        print("Loading articles...")
        self.articles = load_articles(self.jsonl_file)

        print("Building BM25...")
        self.bm25, _ = build_bm25(self.articles)

        print("Loading embedding model...")
        self.embedding_model = EmbeddingRetriever()

        if self.embedding_path.exists():
            print("Loading existing embeddings...")
            self.embeddings = self.embedding_model.load_embeddings(self.embedding_path)
        else:
            print("Building embeddings...")
            self.embedding_path.parent.mkdir(parents=True, exist_ok=True)
            self.embeddings = self.embedding_model.build_embeddings(self.articles)
            self.embedding_model.save_embeddings(self.embeddings, self.embedding_path)

        print("Loading reranker...")
        self.reranker = Reranker()

    def retrieve(self, query, top_k=50, top_n=5, use_bm25=False):
        if use_bm25 == "True":
            candidates = bm25_search(query, self.bm25, self.articles, top_k)
        elif use_bm25 == "False":
            candidates = self.embedding_model.search(query, self.embeddings, self.articles, top_k)
        else:
            candidates = self.embedding_model.search(query, self.embeddings, self.articles, top_k)
            candidates += bm25_search(query, self.bm25, self.articles, top_k)

        return self.reranker.rerank(query, candidates, top_n)
