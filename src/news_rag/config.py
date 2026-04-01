from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
DATA_DIR = PROJECT_ROOT / "data"
DATA_RAW_DIR = DATA_DIR / "raw"
DATA_PROCESSED_DIR = DATA_DIR / "processed"
DATA_CACHE_DIR = DATA_DIR / "cache"
DATA_EVAL_DIR = DATA_DIR / "eval"
DOCS_DIR = PROJECT_ROOT / "docs"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
EVALUATION_OUTPUT_DIR = OUTPUTS_DIR / "evaluation"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
FRONTEND_PUBLIC_DIR = FRONTEND_DIR / "public"

DEFAULT_ARTICLES_FILE = DATA_RAW_DIR / "articles.json"
DEFAULT_DATA_JSONL_FILE = DATA_PROCESSED_DIR / "data.jsonl"
DEFAULT_TRAINING_JSONL_FILE = DATA_PROCESSED_DIR / "training_data.jsonl"
DEFAULT_EMBEDDINGS_FILE = DATA_CACHE_DIR / "embeddings.npy"
DEFAULT_EVAL_ANSWERS_FILE = DATA_EVAL_DIR / "answers_100.jsonl"
DEFAULT_ACTIVE_CORPUS = "first100"


def resolve_corpus_paths(corpus: str = DEFAULT_ACTIVE_CORPUS) -> tuple[Path, Path]:
    normalized = (corpus or "full").strip().lower()
    if normalized == "full":
        return DEFAULT_DATA_JSONL_FILE, DEFAULT_EMBEDDINGS_FILE

    match = re.fullmatch(r"first(\d+)", normalized)
    if not match:
        raise ValueError(f"Unsupported corpus profile: {corpus}")

    size = match.group(1)
    return DATA_PROCESSED_DIR / f"data_first{size}.jsonl", DATA_CACHE_DIR / f"embeddings_first{size}.npy"


def ensure_runtime_dirs() -> None:
    for path in (
        SRC_DIR,
        DATA_RAW_DIR,
        DATA_PROCESSED_DIR,
        DATA_CACHE_DIR,
        DATA_EVAL_DIR,
        DOCS_DIR,
        OUTPUTS_DIR,
        EVALUATION_OUTPUT_DIR,
        FRONTEND_DIR,
        FRONTEND_PUBLIC_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
