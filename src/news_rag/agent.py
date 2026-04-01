from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import jieba
import requests

from .config import DEFAULT_ACTIVE_CORPUS, DEFAULT_DATA_JSONL_FILE, DEFAULT_EMBEDDINGS_FILE, resolve_corpus_paths
from .retrieval import TwoStageRetriever, bm25_search

OPENAI_API_KEY = "xxxx"
DEFAULT_BASE_URL = "https://xiaoai.plus/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-2024-11-20"

FALLBACK_STOPWORDS = {
    "是",
    "的",
    "了",
    "吗",
    "呢",
    "啊",
    "呀",
    "和",
    "与",
    "及",
    "在",
    "将",
    "把",
    "被",
    "请问",
    "请",
    "一个",
    "一下",
    "什么",
    "哪个",
    "哪位",
    "多少",
    "哪些",
    "谁",
    "哪里",
    "哪儿",
    "何时",
    "什么时候",
    "是否",
    "如何",
    "怎么",
    "怎样",
    "有关",
    "关于",
}


@dataclass
class EvidenceAssessment:
    sufficient: bool
    reason: str
    refinement_queries: List[str]


class NewsRAGAgent:
    def __init__(
        self,
        jsonl_file: str | Path | None = None,
        embedding_path: str | Path | None = None,
        corpus: str = DEFAULT_ACTIVE_CORPUS,
        top_k: int = 50,
        top_n: int = 5,
        retrieval_mode: str = "Combine",
        max_query_rounds: int = 3,
    ) -> None:
        default_jsonl_file, default_embedding_path = resolve_corpus_paths(corpus)
        self.top_k = top_k
        self.top_n = top_n
        self.retrieval_mode = retrieval_mode
        self.max_query_rounds = max(1, max_query_rounds)
        self.retriever = TwoStageRetriever(
            jsonl_file or default_jsonl_file or DEFAULT_DATA_JSONL_FILE,
            embedding_path or default_embedding_path or DEFAULT_EMBEDDINGS_FILE,
        )

    def answer(self, query: str) -> Dict[str, object]:
        initial_queries = self.rewrite_queries(query)
        rewritten_queries = self.rewrite_queries(query, max_queries=3)
        current_queries = initial_queries
        final_queries = initial_queries
        final_docs: List[Dict[str, str]] = []
        assessment = EvidenceAssessment(False, "not_started", [])
        query_rounds: List[Dict[str, object]] = []

        for round_index in range(1, self.max_query_rounds + 1):
            current_docs = self.retrieve_with_queries(query, current_queries)
            current_assessment = self.check_evidence(query, current_docs)
            next_queries = self._plan_next_round_queries(query, current_docs, current_assessment, round_index)
            current_assessment.refinement_queries = next_queries
            query_rounds.append(
                {
                    "round": round_index,
                    "queries": list(current_queries),
                    "assessment": current_assessment,
                    "docs": current_docs,
                }
            )

            final_queries = list(current_queries)
            final_docs = current_docs
            assessment = current_assessment

            if assessment.sufficient or round_index >= self.max_query_rounds or not assessment.refinement_queries:
                break

            current_queries = self._normalize_queries(assessment.refinement_queries)

        context = self.build_context(final_docs)
        answer = self.generate_answer(query, context)

        return {
            "query": query,
            "rewritten_queries": rewritten_queries,
            "assessment": assessment,
            "final_queries": final_queries,
            "query_rounds": query_rounds,
            "docs": final_docs,
            "context": context,
            "answer": answer,
        }

    def evaluate(self, queries: Sequence[str]) -> List[str]:
        return [self.answer(query)["answer"] for query in queries]

    def retrieve_with_queries(self, original_query: str, queries: Sequence[str]) -> List[Dict[str, str]]:
        candidates: List[Dict[str, str]] = []
        for query in queries:
            candidates.extend(self._retrieve_candidates(query))
        deduped = self._dedupe_docs(candidates)
        if not deduped:
            return []
        return self.retriever.reranker.rerank(original_query, deduped, self.top_n)

    def rewrite_queries(self, query: str, max_queries: int = 1) -> List[str]:
        normalized = self._normalize_space(query)
        if max_queries <= 1:
            return [normalized] if normalized else [query.strip()]

        if OPENAI_API_KEY:
            try:
                prompt = (
                    "你是中文新闻检索查询改写助手。请把用户问题改写成适合检索的多角度查询。"
                    "要求: "
                    "1. 删除口语化和冗余表达; "
                    "2. 保留核心实体、事件、时间、地点、身份等约束，不要丢失关键限制; "
                    "3. 返回 {max_queries} 个不同角度的检索查询，其中至少 1 个保持原问题的核心表达角度，"
                    "其余查询从标题化表达、关键词表达、侧重点重排等角度改写; "
                    "4. 不要生成答案，不要解释; "
                    "5. 输出 JSON: {\"queries\": [\"q1\", \"q2\", \"q3\"]}"
                )
                content = self._call_llm_text(prompt.format(max_queries=max_queries), f"用户问题: {query}", OPENAI_API_KEY)
                queries = self._parse_query_list(content)
                if queries:
                    return self._ensure_query_count(queries, query, max_queries)
            except Exception:
                pass

        return self._fallback_rewrite_queries(query, max_queries)

    def check_evidence(self, query: str, docs: Sequence[Dict[str, str]]) -> EvidenceAssessment:
        if not docs:
            return EvidenceAssessment(False, "no_docs", [])

        if OPENAI_API_KEY:
            try:
                review_payload = self._build_evidence_review_payload(query, docs[:5])
                prompt = (
                    "你是中文新闻 RAG 的证据审查助手。"
                    "你需要先判断当前证据是否足以直接回答用户问题。"
                    "如果足够，sufficient=true；如果不足，sufficient=false。"
                    "reason 请简要说明缺少了什么关键信息。"
                    "输出 JSON: {\"sufficient\": true/false, \"reason\": \"...\"}"
                )
                content = self._call_llm_text(prompt, review_payload, OPENAI_API_KEY)
                parsed = self._parse_assessment(content)
                if parsed:
                    return parsed
            except Exception:
                pass

        return EvidenceAssessment(False, "low_overlap", [])

    def build_context(self, docs: Sequence[Dict[str, str]], max_chars: int = 2400) -> str:
        parts: List[str] = []
        current_len = 0
        for index, doc in enumerate(docs, start=1):
            prompt = self._trim_text(doc.get("prompt", ""), 280)
            completion = self._trim_text(doc.get("completion", ""), 520)
            block = f"[证据{index}]\n{prompt}\n{completion}".strip()
            if current_len + len(block) > max_chars:
                break
            parts.append(block)
            current_len += len(block) + 2
        return "\n\n".join(parts)

    def generate_answer(self, query: str, context: str) -> str:
        if OPENAI_API_KEY:
            try:
                return self._call_llm_answer(query, context, OPENAI_API_KEY)
            except Exception:
                pass
        return self._fallback_answer(query, context)

    def merge_queries(self, base_queries: Sequence[str], extra_queries: Sequence[str]) -> List[str]:
        merged: List[str] = []
        seen = set()
        for query in list(base_queries) + list(extra_queries):
            normalized = self._normalize_space(query)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
        return merged

    def _normalize_queries(self, queries: Sequence[str]) -> List[str]:
        return self.merge_queries([], queries)

    def _retrieve_candidates(self, query: str) -> List[Dict[str, str]]:
        if self.retrieval_mode == "True":
            return bm25_search(query, self.retriever.bm25, self.retriever.articles, self.top_k)
        if self.retrieval_mode == "False":
            return self.retriever.embedding_model.search(query, self.retriever.embeddings, self.retriever.articles, self.top_k)
        candidates = self.retriever.embedding_model.search(query, self.retriever.embeddings, self.retriever.articles, self.top_k)
        candidates += bm25_search(query, self.retriever.bm25, self.retriever.articles, self.top_k)
        return candidates

    def _call_llm_answer(self, query: str, context: str, api_key: str) -> str:
        payload = {
            "model": DEFAULT_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是中文新闻问答助手。只允许根据提供的新闻证据回答。"
                        "如果证据不足，请明确说明无法根据当前检索证据准确回答。"
                        "优先给出简洁答案，再补充相关标题或上下文。"
                    ),
                },
                {"role": "user", "content": f"问题: {query}\n\n新闻证据:\n{context}"},
            ],
            "temperature": 0.2,
            "max_tokens": 300,
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        response = requests.post(DEFAULT_BASE_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    def _call_llm_text(self, system_prompt: str, user_prompt: str, api_key: str) -> str:
        payload = {
            "model": DEFAULT_MODEL,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            "temperature": 0.2,
            "max_tokens": 500,
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        response = requests.post(DEFAULT_BASE_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    def _fallback_answer(self, query: str, context: str) -> str:
        lines = [line.strip() for line in context.splitlines() if line.strip()]
        query_tokens = self._content_tokens(query)
        scored_lines = []
        for line in lines:
            score = sum(1 for token in query_tokens if token in line)
            if score:
                scored_lines.append((score, line))
        if scored_lines:
            scored_lines.sort(key=lambda item: item[0], reverse=True)
            return f"未配置大模型接口，基于检索证据的候选答案: {scored_lines[0][1]}"
        return "未配置大模型接口，且当前检索证据不足，无法生成可靠答案。"

    def _dedupe_docs(self, docs: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
        result: List[Dict[str, str]] = []
        seen = set()
        for doc in docs:
            key = (doc.get("prompt", ""), doc.get("completion", ""))
            if key in seen:
                continue
            seen.add(key)
            result.append(doc)
        return result

    def _content_tokens(self, text: str) -> List[str]:
        cleaned = self._normalize_space(text)
        tokens = []
        for token in jieba.cut(cleaned):
            token = token.strip()
            if not token or token in FALLBACK_STOPWORDS:
                continue
            if len(token) == 1 and not token.isdigit():
                continue
            tokens.append(token)
        return tokens

    def _fallback_rewrite_query(self, query: str) -> str:
        cleaned = re.sub(r"[，。；：、！？“”‘’《》【】（）()\[\]\"'`]+", " ", query)
        tokens = [token.strip() for token in jieba.cut(cleaned) if token.strip() and token.strip() not in FALLBACK_STOPWORDS]
        keywords: List[str] = []
        seen = set()
        for token in tokens:
            if len(token) == 1 and not token.isdigit():
                continue
            if token not in seen:
                keywords.append(token)
                seen.add(token)
        return " ".join(keywords) if keywords else query.strip()

    def _fallback_rewrite_queries(self, query: str, max_queries: int) -> List[str]:
        normalized = self._normalize_space(query)
        keywords = self._keyword_terms(query)
        queries: List[str] = [normalized] if normalized else []

        if keywords:
            queries.append(" ".join(keywords[:8]))
        if len(keywords) >= 3:
            salient = sorted(keywords, key=lambda item: (len(item), item.isdigit()), reverse=True)
            queries.append(" ".join(salient[:6]))

        if not queries:
            queries = [query.strip()]
        return self._ensure_query_count(queries, query, max_queries)

    def _fallback_step_back_queries(
        self,
        query: str,
        docs: Sequence[Dict[str, str]],
        max_queries: int,
    ) -> List[str]:
        query_keywords = self._keyword_terms(query)
        doc_keywords: List[str] = []
        for doc in docs[:2]:
            prompt = self._trim_text(doc.get("prompt", ""), 120)
            doc_keywords.extend(self._keyword_terms(prompt))

        merged_terms: List[str] = []
        seen = set()
        for token in query_keywords + doc_keywords:
            if token in seen or len(token) == 1:
                continue
            seen.add(token)
            merged_terms.append(token)

        step_back_queries: List[str] = []
        if merged_terms:
            step_back_queries.append(" ".join(merged_terms[:6]))
        if len(doc_keywords) >= 3:
            step_back_queries.append(" ".join(doc_keywords[:6]))
        if len(merged_terms) >= 4:
            salient = sorted(merged_terms, key=lambda item: (len(item), item.isdigit()), reverse=True)
            step_back_queries.append(" ".join(salient[:6]))

        if not step_back_queries:
            step_back_queries.append(self._fallback_rewrite_query(query))
        return self._ensure_query_count(step_back_queries, query, max_queries)

    def _plan_next_round_queries(
        self,
        query: str,
        docs: Sequence[Dict[str, str]],
        assessment: EvidenceAssessment,
        round_index: int,
        max_queries: int = 3,
    ) -> List[str]:
        if assessment.sufficient:
            return []
        if round_index == 1:
            return self.rewrite_queries(query, max_queries=max_queries)
        if round_index >= 2:
            return self.generate_step_back_queries(query, docs, max_queries=max_queries)
        return []

    def generate_step_back_queries(
        self,
        query: str,
        docs: Sequence[Dict[str, str]],
        max_queries: int = 3,
    ) -> List[str]:
        if OPENAI_API_KEY:
            try:
                review_payload = self._build_evidence_review_payload(query, docs[:5])
                prompt = (
                    "你是中文新闻 RAG 的 step-back 查询生成助手。"
                    "当前证据还不足以直接回答问题，请先分析这个问题要成立所依赖的上位事件、背景脉络、相关人物或相关报道，"
                    "再生成更抽象、更适合补充背景证据的检索查询。"
                    "要求: "
                    "1. 保留核心实体、事件、时间、地点等关键约束; "
                    "2. 先根据问题和当前证据判断缺失的是哪一层背景，再据此生成查询; "
                    "3. 查询可以关注上位事件、相关报道、人物活动或背景脉络，但由你自行分析，不要机械复述原问题; "
                    "4. 不要生成答案，不要解释分析过程; "
                    f"5. 返回 {max_queries} 个查询，彼此角度尽量不同; "
                    "6. 输出 JSON: {\"queries\": [\"...\"]}"
                )
                content = self._call_llm_text(prompt.format(max_queries=max_queries), review_payload, OPENAI_API_KEY)
                queries = self._parse_query_list(content)
                if queries:
                    return self._ensure_query_count(queries, query, max_queries)
            except Exception:
                pass

        return self._fallback_step_back_queries(query, docs, max_queries)

    def _ensure_query_count(self, queries: Sequence[str], original_query: str, max_queries: int) -> List[str]:
        normalized = self._normalize_queries(queries)
        if len(normalized) >= max_queries:
            return normalized[:max_queries]

        normalized_query = self._normalize_space(original_query)
        fallback_candidates = self._normalize_queries(
            [normalized_query] + self._fallback_query_variants(original_query, max_queries=max_queries + 2)
        )
        for candidate in fallback_candidates:
            if candidate in normalized:
                continue
            normalized.append(candidate)
            if len(normalized) >= max_queries:
                break
        return normalized[:max_queries]

    def _fallback_query_variants(self, query: str, max_queries: int = 3) -> List[str]:
        keywords = self._keyword_terms(query)
        variants: List[str] = []
        if keywords:
            variants.append(" ".join(keywords[:8]))
        if len(keywords) >= 3:
            variants.append(" ".join(sorted(keywords, key=len, reverse=True)[:6]))
        if len(keywords) >= 4:
            variants.append(" ".join(keywords[:2] + keywords[-2:]))
        if not variants:
            variants.append(self._normalize_space(query))
        return self._normalize_queries(variants)[:max_queries]

    def _keyword_terms(self, text: str) -> List[str]:
        return self._normalize_queries(self._content_tokens(text))

    def _parse_query_list(self, content: str) -> List[str]:
        try:
            data = self._extract_json(content)
            queries = data.get("queries", [])
            if isinstance(queries, list):
                return [str(item).strip() for item in queries if str(item).strip()]
        except Exception:
            pass
        return []

    def _parse_assessment(self, content: str) -> Optional[EvidenceAssessment]:
        try:
            data = self._extract_json(content)
            sufficient = bool(data.get("sufficient", False))
            reason = str(data.get("reason", "")).strip() or "llm_assessment"
            return EvidenceAssessment(sufficient, reason, [])
        except Exception:
            return None

    def _extract_json(self, content: str) -> Dict[str, object]:
        text = content.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))

    def _build_evidence_review_payload(self, query: str, docs: Sequence[Dict[str, str]]) -> str:
        parts = [f"问题: {query}", "当前检索证据:"]
        for index, doc in enumerate(docs, start=1):
            parts.append(
                f"[证据{index}]\n"
                f"{self._trim_text(doc.get('prompt', ''), 220)}\n"
                f"{self._trim_text(doc.get('completion', ''), 420)}"
            )
        return "\n\n".join(parts)

    def _trim_text(self, text: str, limit: int) -> str:
        normalized = self._normalize_space(text)
        if len(normalized) <= limit:
            return normalized
        return normalized[:limit].rstrip() + "..."

    def _normalize_space(self, text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

