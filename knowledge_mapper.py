"""
KOTOBA·AI 知识库扩展 — M3

KB-1/KB-2 知识映射去重 + KB-3/KB-4 待确认池 + KB-5 TF-IDF 检索。
纯标准库实现（零外部依赖，PyInstaller 兼容），独立可测（同 qa_pipeline.py 风格）。
"""

import hashlib
import json
import math
import os
import re
from collections import Counter
from datetime import datetime

from qa_pipeline import parse_question

PENDING_FILE = "pending_knowledge.json"
INDEX_FILE = "knowledge_index.json"
LEARNED_FILE = "learned_content.json"
INDEX_VERSION = 1
FUZZY_THRESHOLD = 0.5          # 2-gram 重叠度 ≥ 此值判为模糊候选
_WHITESPACE_RE = re.compile(r"\s+")
_NGRAM_STRIP_RE = re.compile(r"[()（）]")
_SOURCE_PRIORITY = {"textbook": 0, "practice": 1, "qa_import": 2, "ai_inferred": 3}


# ---------- 工具 ----------
def load_json(filepath, default=None):
    """安全加载 JSON 文件，文件不存在或损坏时返回默认值。"""
    if default is None:
        default = {}
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default


def save_json(filepath, data):
    """保存 JSON 文件，自动创建目录。"""
    dirname = os.path.dirname(filepath)
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ==================== 待确认池（KB-3 / KB-4） ====================

def pending_key(content: str) -> str:
    """同一内容稳定生成同一 id（sha256 前 12 位），用于去重。"""
    return "pk_" + hashlib.sha256((content or "").strip().encode("utf-8")).hexdigest()[:12]


def load_pending() -> dict:
    return load_json(PENDING_FILE, {"items": []})


def save_pending(pool: dict) -> None:
    save_json(PENDING_FILE, pool)


def collect_pending(content: str, parse_result: dict, level: str = "N4") -> str | None:
    """模式 C 解析结果 → 写入待确认池（KB-3）。重复内容原地刷新，不入新条目。

    返回条目 id；无知识点标签时不收集，返回 None。
    """
    content = (content or "").strip()
    tags = parse_result.get("knowledge_tags") or []
    if not content or not tags:
        return None

    item_id = pending_key(content)
    pool = load_pending()
    item = {
        "id": item_id,
        "content": content,
        "answer_key": "",
        "level": level,
        "knowledge_tags": tags,
        "ai_answer": (parse_result.get("answer") or {}).get("correct_answer", ""),
        "ai_confidence": (parse_result.get("answer") or {}).get("ai_confidence"),
        "explanation": parse_result.get("explanation", ""),
        "question_type": parse_result.get("question_type", ""),
        "mode": "C",
        "status": "pending",
        "created_at": _now(),
        "parsed_at": _now(),
    }
    # 同一内容：已存在则刷新（覆盖为最新解析），否则新增
    for i, old in enumerate(pool["items"]):
        if old.get("id") == item_id:
            old["status"] = "pending"
            old["knowledge_tags"] = tags
            old["ai_answer"] = item["ai_answer"]
            old["ai_confidence"] = item["ai_confidence"]
            old["explanation"] = item["explanation"]
            old["question_type"] = item["question_type"]
            old["parsed_at"] = item["parsed_at"]
            if not old.get("created_at"):
                old["created_at"] = item["created_at"]
            save_pending(pool)
            return item_id
    pool["items"].append(item)
    save_pending(pool)
    return item_id


def list_pending(status: str = "pending") -> list:
    """列出待确认池条目（响应用：内容截断为预览，不含完整原文）。"""
    pool = load_pending()
    items = [it for it in pool["items"] if it.get("status", "pending") == status]
    items.sort(key=lambda x: x.get("parsed_at", ""), reverse=True)
    result = []
    for it in items:
        display = dict(it)
        display["content_preview"] = (it.get("content") or "")[:150]
        display.pop("content", None)
        result.append(display)
    return result


def confirm_pending(ids: list) -> dict:
    """确认待确认池条目 → 知识映射节点 → 去重入库 learned_content（KB-3）。

    返回：{confirmed, fuzzy, learned_count}。fuzzy 是需要用户进一步确认的模糊匹配候选。
    """
    ids = [str(i) for i in (ids or [])]
    if not ids:
        raise ValueError("请选择要确认的知识点")
    pool = load_pending()
    learned = load_json(LEARNED_FILE, {"items": []})
    learned_items = learned.get("items", [])
    textbook = load_textbook_grammar()

    confirmed_count = 0
    fuzzy_report = []
    to_keep = []

    for it in pool["items"]:
        if it.get("id") not in ids:
            to_keep.append(it)
            continue
        if it.get("status", "pending") != "pending":
            to_keep.append(it)
            continue
        tags = it.get("knowledge_tags") or []
        for tag in tags:
            mapped = map_knowledge(
                [tag],
                learned_items,
                textbook,
                source_context={"pending_id": it["id"]},
            )
            if mapped["fuzzy"]:
                fuzzy_report.extend(mapped["fuzzy"])
                continue
            learned_items = _upsert_learned(learned_items, mapped["resolved"][0])
        confirmed_count += 1

    pool["items"] = to_keep
    save_pending(pool)
    learned["items"] = learned_items
    save_json(LEARNED_FILE, learned)
    return {
        "confirmed": confirmed_count,
        "fuzzy": fuzzy_report,
        "learned_count": len(learned_items),
    }


def discard_pending(ids: list) -> int:
    """从待确认池删除条目，返回删除数。"""
    ids = [str(i) for i in (ids or [])]
    if not ids:
        raise ValueError("请选择要丢弃的知识点")
    pool = load_pending()
    before = len(pool["items"])
    pool["items"] = [it for it in pool["items"] if it.get("id") not in ids]
    save_pending(pool)
    return before - len(pool["items"])


def reparse_pending(item_id: str, answer_key: str, call_llm, level: str = "N4") -> dict:
    """补充答案键后整题重新解析，覆盖 AI 推断（KB-4）。

    以模式 A 重新解析原文，更新 pending 条目（清 ai_inferred、填 answer_key），
    status 保持 pending 待用户最终确认。返回 {item, result}。
    """
    item_id = str(item_id or "")
    answer_key = (answer_key or "").strip()
    if not item_id:
        raise ValueError("缺少条目 id")
    if not answer_key:
        raise ValueError("请先填写标准答案")

    pool = load_pending()
    item = next((it for it in pool["items"] if it.get("id") == item_id), None)
    if item is None:
        raise ValueError("待确认条目不存在，可能已被删除")

    # 模式 A 重新解析（有答案键）
    result = parse_question(
        content=item.get("content", ""),
        answer_key=answer_key,
        level=level,
        call_llm=call_llm,
    )
    # 覆盖推断：重新解析的知识点不再标 ai_inferred
    item["answer_key"] = answer_key
    item["knowledge_tags"] = result.get("knowledge_tags") or []
    item["ai_answer"] = (result.get("answer") or {}).get("correct_answer", "")
    item["ai_confidence"] = None
    item["explanation"] = result.get("explanation", "")
    item["mode"] = "A"
    item["parsed_at"] = _now()
    save_pending(pool)
    return {"item": item, "result": result}


# ==================== 知识映射节点（KB-1 / KB-2） ====================

def normalize_point(name: str) -> str:
    """规范化知识点名：去空白、去 〜～、去括号，供精确匹配。"""
    name = (name or "").strip()
    name = _WHITESPACE_RE.sub("", name)
    name = name.replace("〜", "").replace("～", "")
    name = _NGRAM_STRIP_RE.sub("", name)
    return name


def load_textbook_grammar() -> list:
    """遍历教材索引，收集全部语法点 → [{point, explanation, textbook_ref}]。"""
    index = load_json("knowledge_base/index.json", {"textbooks": []})
    result = []
    for tb in index.get("textbooks", []):
        tb_id = tb.get("id", "")
        for vol in tb.get("volumes", []):
            file_path = os.path.join("knowledge_base", vol.get("file", ""))
            data = load_json(file_path, None)
            if not data:
                continue
            for lesson in data.get("lessons", []):
                lesson_no = lesson.get("lesson")
                for gp in lesson.get("grammar", []):
                    point = gp.get("point", "")
                    if not point:
                        continue
                    result.append({
                        "point": point,
                        "explanation": gp.get("explanation", ""),
                        "textbook_ref": {
                            "textbook": tb_id,
                            "volume": vol.get("id", ""),
                            "lesson": lesson_no,
                            "point": point,
                        },
                    })
    return result


def _bigram_overlap(a: str, b: str) -> float:
    """两个字符串的 2-gram 重叠度（Jaccard），用于模糊匹配。"""
    def grams(s):
        s = _WHITESPACE_RE.sub("", s or "")
        if len(s) < 2:
            return {s} if s else set()
        return {s[i:i + 2] for i in range(len(s) - 1)}
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def _source_of(learned_item: dict) -> str:
    """已学条目的来源（默认 practice），按权威性排序后取最强。"""
    sources = (learned_item.get("source") or "").split(",")
    sources = [s for s in sources if s]
    sources.sort(key=lambda s: _SOURCE_PRIORITY.get(s, 9))
    return sources[0] if sources else "practice"


def map_knowledge(tags: list, learned_items: list, textbook: list = None,
                  source_context: dict = None) -> dict:
    """映射单条知识点到 canonical 形态（KB-2 四分支）。

    - 精确匹配教材语法点 → textbook_merge（source="textbook"，挂 textbook_ref）
    - 精确匹配已有 learned 条目 → existing_merge（更新 linked_qa_items）
    - 模糊匹配已有条目（2-gram 重叠 ≥ 阈值）→ fuzzy（需用户确认，不入库）
    - 未命中 → create_new（source="qa_import"）

    返回 {"resolved": [dict], "fuzzy": [dict]}。
    """
    if textbook is None:
        textbook = load_textbook_grammar()
    source_context = source_context or {}
    pending_id = source_context.get("pending_id", "")

    resolved, fuzzy = [], []
    textbook_map = {normalize_point(t["point"]): t for t in textbook}
    learned_map = {normalize_point(it.get("grammar_point", "")): it for it in learned_items}

    for raw in tags:
        if not isinstance(raw, dict):
            raw = {"tag": str(raw), "type": "grammar"}
        tag = str(raw.get("tag", "")).strip()
        typ = raw.get("type", "grammar")
        if not tag:
            continue
        ntag = normalize_point(tag)

        # ① 教材精确匹配 → 以教材为权威锚点
        if ntag in textbook_map:
            tb = textbook_map[ntag]
            resolved.append({
                "tag": tag, "type": typ,
                "decision": "textbook_merge",
                "source": "textbook",
                "textbook_ref": tb["textbook_ref"],
                "explanation": tb["explanation"],
                "pending_id": pending_id,
            })
            continue

        # ② 已有条目精确匹配 → 合并（不重复建条目）
        if ntag in learned_map:
            resolved.append({
                "tag": tag, "type": typ,
                "decision": "existing_merge",
                "source": _source_of(learned_map[ntag]),
                "textbook_ref": learned_map[ntag].get("textbook_ref"),
                "existing": learned_map[ntag],
                "pending_id": pending_id,
            })
            continue

        # ③ 模糊匹配 → 待用户确认（不自动入库，防止近重复）
        candidates = []
        for other in learned_items:
            other_name = str(other.get("grammar_point", ""))
            if not other_name:
                continue
            sim = _bigram_overlap(ntag, normalize_point(other_name))
            if sim >= FUZZY_THRESHOLD:
                candidates.append({"grammar_point": other_name, "similarity": round(sim, 2)})
        if candidates:
            candidates.sort(key=lambda c: c["similarity"], reverse=True)
            fuzzy.append({
                "tag": tag, "type": typ,
                "suggestions": candidates[:3],
            })
            continue

        # ④ 未命中 → 新建
        resolved.append({
            "tag": tag, "type": typ,
            "decision": "create_new",
            "source": "qa_import",
            "textbook_ref": None,
            "pending_id": pending_id,
        })

    return {"resolved": resolved, "fuzzy": fuzzy}


def _upsert_learned(learned_items: list, mapped: dict) -> list:
    """把映射结果写入 learned_content 条目列表（幂等，不重置 SM-2 数据）。"""
    gp = mapped["tag"].strip()
    normalized = normalize_point(gp)

    # 先找已存在条目（规范名匹配）
    for item in learned_items:
        if normalize_point(item.get("grammar_point", "")) == normalized:
            if mapped.get("decision") == "textbook_merge":
                item["source"] = mapped["source"]
                item["textbook_ref"] = mapped["textbook_ref"]
            # 已有来源更强则保留（textbook 最强）
            if item.get("source") in (None, ""):
                item["source"] = mapped["source"]
            if item.get("textbook_ref") is None and mapped.get("textbook_ref"):
                item["textbook_ref"] = mapped["textbook_ref"]
            item["type"] = mapped.get("type", item.get("type", "grammar"))
            linked = item.setdefault("linked_qa_items", [])
            if mapped.get("pending_id") and mapped["pending_id"] not in linked:
                linked.append(mapped["pending_id"])
            return learned_items

    # 不存在 → 新建（含 SM-2 初始字段，mastery 从 0 开始，等练习/复习打分推进）
    today = datetime.now().strftime("%Y-%m-%d")
    new_item = {
        "grammar_point": gp,
        "level": "N4",
        "source": mapped["source"],
        "type": mapped.get("type", "grammar"),
        "textbook_ref": mapped.get("textbook_ref"),
        "linked_qa_items": [mapped["pending_id"]] if mapped.get("pending_id") else [],
        "first_learned": today,
        "last_reviewed": today,
        "review_count": 0,
        "review_stage": 0,
        "review_interval": 1,
        "next_review": today,
        "mastery": 0.0,
        "history_scores": [],
    }
    if mapped.get("explanation"):
        new_item["note"] = mapped["explanation"]
    learned_items.append(new_item)
    return learned_items


# ==================== TF-IDF 检索（KB-5） ====================

def tokenize(text: str, n: int = 2) -> list:
    """character n-gram 分词（日语无空格，2-gram 兼顾假名与汉字）。"""
    text = _NGRAM_STRIP_RE.sub("", text or "")
    text = _WHITESPACE_RE.sub("", text)
    if len(text) < n:
        return [text] if text else []
    return [text[i:i + n] for i in range(len(text) - n + 1)]


def build_corpus() -> list:
    """构建检索语料：教材语法点 + learned_content 条目。"""
    entries = []
    for gp in load_textbook_grammar():
        entries.append({
            "id": f"textbook:{gp['textbook_ref']['volume']}:L{gp['textbook_ref']['lesson']}:{gp['point']}",
            "name": gp["point"],
            "type": "grammar",
            "source": "textbook",
            "textbook_ref": gp["textbook_ref"],
            "explanation": gp["explanation"],
        })
    learned = load_json(LEARNED_FILE, {"items": []})
    for it in learned.get("items", []):
        gp = it.get("grammar_point", "")
        if not gp:
            continue
        entries.append({
            "id": f"learned:{gp}",
            "name": gp,
            "type": it.get("type", "grammar"),
            "source": _source_of(it),
            "textbook_ref": it.get("textbook_ref"),
            "explanation": it.get("note", ""),
        })
    return entries


def rebuild_index() -> int:
    """重建 knowledge_index.json，返回语料条目数。"""
    corpus = build_corpus()
    doc_tokens = []
    for e in corpus:
        text = e["name"] + " " + (e["explanation"] or "")
        tokens = set(tokenize(text))
        e["tokens"] = sorted(tokens)
        doc_tokens.append(tokens)

    n = len(doc_tokens)
    df = Counter()
    for tokens in doc_tokens:
        df.update(tokens)
    idf = {t: math.log(n / (1 + df[t])) for t in df}
    idf["_default"] = math.log(n + 1)

    index = {
        "version": INDEX_VERSION,
        "built_at": _now(),
        "corpus_size": n,
        "idf": idf,
        "entries": corpus,
    }
    save_json(INDEX_FILE, index)
    return n


def load_index() -> dict:
    """加载索引；不存在或版本不符时自动重建。"""
    index = load_json(INDEX_FILE, None)
    if not index or index.get("version") != INDEX_VERSION:
        rebuild_index()
        index = load_json(INDEX_FILE, None)
    return index or {"idf": {}, "entries": []}


def retrieve_top_k(query: str, k: int = 3) -> list:
    """TF-IDF 检索 top-k 相关知识条目。"""
    query = (query or "").strip()
    if not query:
        return []
    index = load_index()
    idf = index.get("idf", {})
    entries = index.get("entries", [])
    if not entries:
        return []

    q_tokens = Counter(tokenize(query))
    results = []
    for e in entries:
        entry_tokens = set(e.get("tokens", []))
        score = 0.0
        for t, qtf in q_tokens.items():
            if t in entry_tokens:
                score += idf.get(t, idf.get("_default", 1.0)) * qtf
        norm = math.sqrt(len(entry_tokens))
        score = score / max(norm, 1.0)
        if score > 0:
            results.append({
                "id": e["id"],
                "name": e["name"],
                "type": e["type"],
                "source": e["source"],
                "textbook_ref": e.get("textbook_ref"),
                "explanation": e.get("explanation", ""),
                "score": round(score, 4),
            })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:k]


def build_qa_knowledge_context(query: str, k: int = 3) -> str:
    """答疑 prompt 用：检索 top-3 相关知识 → markdown 段。无命中返回空串。"""
    results = retrieve_top_k(query, k=k)
    if not results:
        return ""
    lines = ["## 相关已学知识"]
    for r in results:
        lines.append(f"- {r['name']}（{r['type']}）：{r['explanation'] or '（暂无讲解）'}")
    return "\n".join(lines)
