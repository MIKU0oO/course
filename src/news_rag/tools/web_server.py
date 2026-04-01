import argparse
import json
import mimetypes
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from ..config import DEFAULT_ACTIVE_CORPUS, DEFAULT_DATA_JSONL_FILE, FRONTEND_PUBLIC_DIR, ensure_runtime_dirs, resolve_corpus_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="中文新闻 RAG 网页服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--corpus", default=DEFAULT_ACTIVE_CORPUS, help="语料配置，例如 full 或 first100")
    parser.add_argument("--data-file", help="检索语料 jsonl 文件，显式指定时覆盖 --corpus")
    parser.add_argument("--embedding-file", help="embedding 文件，显式指定时覆盖 --corpus")
    parser.add_argument("--top-k", type=int, default=50, help="每轮召回数量")
    parser.add_argument("--top-n", type=int, default=5, help="每轮重排后保留数量")
    parser.add_argument("--max-query-rounds", type=int, default=3, help="最大查询轮次")
    parser.add_argument("--mode", default="Combine", choices=["Combine", "True", "False"], help="检索模式")
    return parser


def parse_doc_metadata(prompt: str) -> dict:
    lines = [line.strip() for line in prompt.splitlines() if line.strip()]
    title = ""
    url = ""
    publish_time = ""
    chunk = ""

    for line in lines:
        if line.startswith("URL:"):
            url = line.split(":", 1)[1].strip()
            continue
        if "/" in line and not chunk and any(char.isdigit() for char in line):
            chunk = line.split(":", 1)[1].strip() if ":" in line else line
            continue
        if ":" in line:
            label, value = line.split(":", 1)
            label = label.strip().lower()
            value = value.strip()
            if not title and label != "url":
                title = value
            elif not publish_time and "url" not in label:
                publish_time = value
        elif not title:
            title = line

    return {
        "title": title,
        "url": url,
        "publish_time": publish_time,
        "chunk": chunk,
    }


def clean_snippet(text: str, limit: int = 260) -> str:
    normalized = " ".join((text or "").replace("\u3000", " ").split())
    for prefix in ("内容:", "鍐呭:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):].strip()
            break
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "..."


class SearchApp:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self._agent = None
        self._agent_lock = threading.Lock()
        self._search_lock = threading.Lock()
        self.static_root = FRONTEND_PUBLIC_DIR

    def get_agent(self):
        if self._agent is not None:
            return self._agent
        with self._agent_lock:
            if self._agent is None:
                from ..agent import NewsRAGAgent
                default_data_file, default_embedding_file = resolve_corpus_paths(self.args.corpus)

                self._agent = NewsRAGAgent(
                    jsonl_file=self.args.data_file or default_data_file or DEFAULT_DATA_JSONL_FILE,
                    embedding_path=self.args.embedding_file or default_embedding_file,
                    corpus=self.args.corpus,
                    top_k=self.args.top_k,
                    top_n=self.args.top_n,
                    retrieval_mode=self.args.mode,
                    max_query_rounds=self.args.max_query_rounds,
                )
        return self._agent

    def search(self, query: str) -> dict:
        start = time.time()
        with self._search_lock:
            result = self.get_agent().answer(query)
        elapsed_ms = int((time.time() - start) * 1000)

        docs = []
        for index, doc in enumerate(result["docs"], start=1):
            meta = parse_doc_metadata(doc.get("prompt", ""))
            docs.append(
                {
                    "rank": index,
                    "doc_id": doc.get("doc_id"),
                    "chunk_id": doc.get("chunk_id"),
                    "chunk_total": doc.get("chunk_total"),
                    "title": meta["title"],
                    "url": meta["url"],
                    "publish_time": meta["publish_time"],
                    "chunk": meta["chunk"],
                    "snippet": clean_snippet(doc.get("completion", "")),
                    "prompt": doc.get("prompt", ""),
                    "completion": doc.get("completion", ""),
                }
            )

        return {
            "query": result["query"],
            "answer": result["answer"],
            "context": result["context"],
            "rewritten_queries": result["rewritten_queries"],
            "final_queries": result["final_queries"],
            "assessment": {
                "sufficient": result["assessment"].sufficient,
                "reason": result["assessment"].reason,
                "refinement_queries": result["assessment"].refinement_queries,
            },
            "query_rounds": [
                {
                    "round": item["round"],
                    "queries": item["queries"],
                    "assessment": {
                        "sufficient": item["assessment"].sufficient,
                        "reason": item["assessment"].reason,
                        "refinement_queries": item["assessment"].refinement_queries,
                    },
                    "doc_count": len(item.get("docs", [])),
                }
                for item in result["query_rounds"]
            ],
            "docs": docs,
            "stats": {
                "elapsed_ms": elapsed_ms,
                "doc_count": len(docs),
                "corpus": self.args.corpus,
                "mode": self.args.mode,
                "top_k": self.args.top_k,
                "top_n": self.args.top_n,
                "max_query_rounds": self.args.max_query_rounds,
            },
        }


def make_handler(app: SearchApp):
    class RequestHandler(BaseHTTPRequestHandler):
        server_version = "NewsRAGWeb/0.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                self._send_json({"status": "ok"})
                return
            self._serve_static(parsed.path)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/search":
                self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
                return

            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._send_json({"error": "请求体必须是合法 JSON"}, status=HTTPStatus.BAD_REQUEST)
                return

            query = str(payload.get("query", "")).strip()
            if not query:
                self._send_json({"error": "query 不能为空"}, status=HTTPStatus.BAD_REQUEST)
                return

            try:
                response = app.search(query)
            except Exception as exc:
                self._send_json(
                    {
                        "error": "搜索失败",
                        "detail": str(exc),
                    },
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return

            self._send_json(response)

        def _serve_static(self, raw_path: str) -> None:
            relative = raw_path.strip("/") or "index.html"
            relative = unquote(relative)
            target = (app.static_root / relative).resolve()
            static_root = app.static_root.resolve()

            if not str(target).startswith(str(static_root)) or not target.exists() or not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
                return

            content_type, _ = mimetypes.guess_type(str(target))
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(target.read_bytes())

        def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:
            return

    return RequestHandler


def run_web_server() -> None:
    ensure_runtime_dirs()
    args = build_parser().parse_args()
    app = SearchApp(args)
    handler = make_handler(app)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    address = f"http://{args.host}:{args.port}"
    print(f"网页服务已启动: {address}")
    print("按 Ctrl+C 停止服务")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    run_web_server()
