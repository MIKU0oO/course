#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from ..config import DEFAULT_DATA_JSONL_FILE, DEFAULT_EVAL_ANSWERS_FILE, DATA_EVAL_DIR, ensure_runtime_dirs


TIME_PREFIX_RE = re.compile(
    r"^(?:截至[^，。；]{0,12}|今年以来|去年以来|今年|去年|目前|近日|日前|近年|最近|当日|同日|"
    r"本届|本次|当天|其中|同时|此外|据[^，。；]{0,15}|记者[^，。；]{0,20}|内容:|"
    r"\d{4}年\d{1,2}月\d{1,2}日，)+"
)

GENERIC_SUBJECTS = {
    "每年", "组织", "我们", "有关部门", "相关部门", "相关方面", "有关方面", "各地",
    "全国范围内", "全国", "目前", "今年", "去年", "也是", "其中", "此外",
}

BAD_ANNIVERSARY_PREFIXES = (
    "隆重庆祝", "恰逢", "即将迎来", "迎来", "一是迎来", "我们迎来",
    "庆祝", "也是", "正值", "值此", "迎接", "是", "《",
)

BAD_COUNT_TOKENS = {
    "他", "她", "它", "我们", "携手", "同步", "如今", "由", "这里", "文旅带", "通报了", "新增了", "开通后",
}

BAD_PHRASES = {
    "主持", "考察并", "工作会议", "全国范围内", "各地", "最大", "问题",
    "情况", "由", "其中", "目前", "今年", "去年", "也是", "按计划于", "前身",
}

EVENT_KEYWORDS = {
    "峰会", "论坛", "大会", "年会", "博览会", "书展", "仪式", "活动", "比赛",
    "展演", "对话会", "圆桌会", "招聘会", "传递", "会展", "书博会", "展览会", "启动仪式",
}

BAD_LOCATION_TOKENS = {"其官网上", "为住院患儿", "圆满", "隆重", "新闻", "工作组会"}


@dataclass
class Candidate:
    question: str
    answer: str
    question_type: str
    score: int
    source: Dict[str, object]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据 data.jsonl 生成测试题")
    parser.add_argument("--input", default=str(DEFAULT_DATA_JSONL_FILE), help="输入 jsonl 文件")
    parser.add_argument("--count", type=int, default=100, help="题目数量")
    parser.add_argument("--answers-out", default=str(DEFAULT_EVAL_ANSWERS_FILE), help="答案 jsonl 输出路径")
    parser.add_argument("--answers-txt-out", default=str(DATA_EVAL_DIR / "answers_100.txt"), help="答案 txt 输出路径")
    return parser.parse_args()


def parse_prompt_metadata(prompt: str) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    for raw_line in prompt.splitlines():
        line = raw_line.strip()
        if line.startswith("标题: "):
            meta["title"] = line[4:]
        elif line.startswith("URL: "):
            meta["url"] = line[5:]
        elif line.startswith("发布时间: "):
            meta["publish_time"] = line[6:]
        elif line.startswith("分块: "):
            meta["chunk_info"] = line[4:]
    return meta


def clean_completion(text: str) -> str:
    cleaned = text.replace("内容:", "").replace("■", "").replace("\xa0", "").strip()
    return re.sub(r"\s+", "", cleaned)


def clean_fragment(text: str) -> str:
    cleaned = TIME_PREFIX_RE.sub("", text)
    cleaned = re.sub(r"^为期[^的]{1,8}的", "", cleaned)
    cleaned = re.split(r"[，。；：]", cleaned)[-1]
    cleaned = re.sub(r"（[^）]{0,8}）", "", cleaned)
    cleaned = re.sub(r"\([^)]{0,8}\)", "", cleaned)
    if cleaned.count("（") > cleaned.count("）"):
        cleaned = re.split(r"[（(]", cleaned)[0]
    if cleaned.count("(") > cleaned.count(")"):
        cleaned = cleaned.split("(", 1)[0]
    cleaned = cleaned.strip("，。；：、 “”‘’()（）")
    cleaned = re.sub(r"^(由|在|于|对|把|将|使|让|为|围绕|针对)", "", cleaned)
    cleaned = re.sub(r"(已经|已|累计|共)$", "", cleaned)
    return cleaned[:40]


def is_bad_fragment(text: str) -> bool:
    return not text or text in GENERIC_SUBJECTS or any(phrase in text for phrase in BAD_PHRASES)


def extract_candidates(record: Dict[str, object]) -> Iterable[Candidate]:
    prompt = str(record.get("prompt", ""))
    completion = clean_completion(str(record.get("completion", "")))
    if not completion:
        return []

    meta = parse_prompt_metadata(prompt)
    source = {
        "doc_id": record.get("doc_id"),
        "chunk_id": record.get("chunk_id"),
        "chunk_total": record.get("chunk_total"),
        "title": meta.get("title", ""),
        "url": meta.get("url", ""),
        "publish_time": meta.get("publish_time", ""),
    }
    candidates: List[Candidate] = []

    event_match = re.search(
        r"(\d{1,2}月\d{1,2}日(?:至\d{1,2}日)?)，([^。；\n]{2,60}?)(?:在|于)([^，。；\n]{2,30}?)(召开|举行|举办|开幕|闭幕|启动|发布|举行了|举办了)",
        completion,
    )
    if event_match:
        date, subject, location, verb = event_match.groups()
        subject = clean_fragment(subject)
        location = location.strip("，。；：、 ")
        if (
            4 <= len(subject) <= 30 and 2 <= len(location) <= 24
            and not is_bad_fragment(subject) and not is_bad_fragment(location)
            and any(keyword in subject for keyword in EVENT_KEYWORDS)
            and not any(token in location for token in BAD_LOCATION_TOKENS)
        ):
            score = 90 + (10 if 6 <= len(subject) <= 18 else 0) + (5 if 2 <= len(location) <= 12 else 0)
            candidates.append(Candidate(f"{date}{subject}在哪里{verb}？", location, "event_location", score, source))

    anniversary_match = re.search(r"(?:庆祝|纪念|迎来)?([^，。；\n]{2,24}?)(?:成立|创立)([0-9一二三四五六七八九十百千万两零〇]+)周年", completion)
    if anniversary_match:
        subject, number = anniversary_match.groups()
        subject = clean_fragment(subject)
        for prefix in BAD_ANNIVERSARY_PREFIXES:
            if subject.startswith(prefix):
                subject = subject[len(prefix):]
        if (
            2 <= len(subject) <= 20 and not re.search(r"\d", subject)
            and not is_bad_fragment(subject) and "迎来" not in subject and "我们" not in subject
            and "庆祝" not in subject and "《" not in subject and not subject.startswith(("是", "迎接"))
        ):
            score = 85 + (10 if 3 <= len(subject) <= 10 else 0)
            candidates.append(Candidate(f"文中提到，{subject}成立多少周年？", f"{number}周年", "anniversary", score, source))

    count_match = re.search(
        r"([^。；\n]{2,50}?)(发布|完成|实施|检查|查处|召回|签署|建成|开通|发送)([^。；\n]{0,20}?)(\d+(?:\.\d+)?(?:万)?(?:余)?)(项|批次|家次|件|份|场|条|次|名|人次|亿元|万人|万件)",
        completion,
    )
    if count_match:
        subject, verb, obj_text, number, unit = count_match.groups()
        subject = clean_fragment(subject)
        obj_text = obj_text.strip("，。；：、 ")
        combined_phrase = f"{subject}{verb}{obj_text}"
        bad_obj_tokens = {"确保", "达到", "稳定在", "以上", "以下", "左右", "约", "超过", "近"}
        if (
            2 <= len(subject) <= 20 and len(obj_text) <= 12
            and not is_bad_fragment(subject)
            and not any(token in subject for token in BAD_COUNT_TOKENS)
            and not any(token in obj_text for token in bad_obj_tokens)
            and not re.search(r"[0-9“”\"']", subject)
            and not re.search(r"[0-9“”\"']", obj_text)
            and "公开通报" not in subject and "新增" not in subject and "开通后" not in subject
            and "公开通报" not in combined_phrase and "开通后" not in combined_phrase and "新增了" not in combined_phrase
            and "，" not in subject and not subject.endswith(("了", "后"))
        ):
            score = 80 + (5 if subject not in GENERIC_SUBJECTS else 0) + (5 if obj_text else 0)
            candidates.append(Candidate(f"文中提到，{subject}{verb}{obj_text}多少{unit}？", f"{number}{unit}", "count", score, source))

    return candidates


def dedupe_candidates(candidates: Iterable[Candidate]) -> List[Candidate]:
    best: Dict[str, Candidate] = {}
    for candidate in candidates:
        existing = best.get(candidate.question)
        if existing is None or candidate.score > existing.score:
            best[candidate.question] = candidate
    return list(best.values())


def select_candidates(candidates: List[Candidate], target_count: int) -> List[Candidate]:
    ordered = sorted(
        candidates,
        key=lambda item: (-item.score, int(item.source.get("doc_id") or 0), int(item.source.get("chunk_id") or 0), item.question),
    )
    quotas = {"event_location": 70, "count": 22, "anniversary": 8}

    selected: List[Candidate] = []
    used_questions = set()
    doc_counts: Dict[object, int] = {}
    type_counts: Dict[str, int] = {}

    def try_take(item: Candidate, enforce_quota: bool) -> bool:
        doc_id = item.source.get("doc_id")
        if item.question in used_questions or doc_counts.get(doc_id, 0) >= 1:
            return False
        if enforce_quota and type_counts.get(item.question_type, 0) >= quotas.get(item.question_type, 0):
            return False
        selected.append(item)
        used_questions.add(item.question)
        doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1
        type_counts[item.question_type] = type_counts.get(item.question_type, 0) + 1
        return True

    for item in ordered:
        try_take(item, enforce_quota=True)
    if len(selected) < target_count:
        for item in ordered:
            if len(selected) >= target_count:
                break
            try_take(item, enforce_quota=False)
    return selected[:target_count]


def write_answers_txt(path: Path, items: List[Candidate]) -> None:
    blocks: List[str] = []
    for index, item in enumerate(items, start=1):
        source_json = json.dumps({**item.source, "question_type": item.question_type}, ensure_ascii=False)
        blocks.append("\n".join([f"{index}. 问题: {item.question}", f"答案: {item.answer}", f"出处JSON: {source_json}"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def write_answers_jsonl(path: Path, items: List[Candidate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for index, item in enumerate(items, start=1):
        lines.append(
            json.dumps(
                {
                    "id": index,
                    "question": item.question,
                    "answer": item.answer,
                    "question_type": item.question_type,
                    "source": item.source,
                },
                ensure_ascii=False,
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_records(path: Path) -> Iterable[Dict[str, object]]:
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                yield json.loads(line)


def main() -> None:
    ensure_runtime_dirs()
    args = parse_args()
    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"找不到输入文件: {input_path}")

    raw_candidates: List[Candidate] = []
    for record in load_records(input_path):
        raw_candidates.extend(extract_candidates(record))

    selected = select_candidates(dedupe_candidates(raw_candidates), args.count)
    if len(selected) < args.count:
        raise RuntimeError(f"只生成了 {len(selected)} 道题，未达到目标数量 {args.count}")

    write_answers_jsonl(Path(args.answers_out), selected)
    write_answers_txt(Path(args.answers_txt_out), selected)

    print(f"已生成 {len(selected)} 道题。")
    print(f"答案 JSONL: {Path(args.answers_out).resolve()}")
    print(f"答案 TXT: {Path(args.answers_txt_out).resolve()}")


if __name__ == "__main__":
    main()
