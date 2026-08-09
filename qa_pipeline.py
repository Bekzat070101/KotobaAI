"""
KOTOBA·AI 答疑（QA）管线 — M1

QP-1 分类路由 + QP-2 三模式（A/B/C）分流 + QP-3 确定性判分 + CC-1 缓存。
LLM 调用通过 call_llm(prompt, require_json) 注入，便于测试用 stub 替换。
"""

import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta

from prompts.qa_parse import VALID_TYPES, build_classify_prompt, build_parse_prompt

CACHE_FILE = os.path.join("cache", "qa_cache.json")
CACHE_TTL_DAYS = 30          # CC-1：冷数据 30 天清理
MAX_QA_LENGTH = 50000        # 题目内容最大长度
MAX_TAGS = 10                # 单个结果最多保留知识点数

_KANA_RE = re.compile(r"[぀-ヿ]")      # 平假名 + 片假名
_JP_ONLY_RE = re.compile(r"[々・]")            # 日本特有字符（汉字无法区分中日）
_BLANK_PATTERNS = [r"＿+", r"（\s*）", r"\(\s*\)", r"【\s*】", r"_{2,}"]


# ---------- QP-2：模式判定 ----------
def detect_mode(answer_key: str = "", user_answer: str = "") -> str:
    """A：有答案键（确定性判分）；B：有用户作答（AI 评判）；C：纯题目（AI 解题）。"""
    if answer_key and answer_key.strip():
        return "A"
    if user_answer and user_answer.strip():
        return "B"
    return "C"


# ---------- QP-3：确定性判分（不用 LLM 判对错） ----------
def _normalize(text: str) -> str:
    """归一化：NFKC（全角→半角）+ 去空白 + 去标点 + 小写。"""
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[。、，,.!?！？；;：:「」『』（）()【】\[\]～]", "", text)
    return text.lower()


def deterministic_grade(user_answer: str, answer_key: str) -> dict:
    """模式 A 专用：答案与答案键逐项确定性对比，结果无 AI 介入。"""
    nu = _normalize(user_answer)
    nk = _normalize(answer_key)
    return {
        "is_correct": bool(nu) and bool(nk) and nu == nk,
        "normalized_user": nu,
        "normalized_key": nk,
    }


# ---------- QP-1：分类（LLM + 规则回退） ----------
def contains_japanese(text: str) -> bool:
    """是否含日文假名或日本特有字符（汉字单独无法区分中日，不用作判据）。"""
    return bool(_KANA_RE.search(text or "")) or bool(_JP_ONLY_RE.search(text or ""))


def rule_based_classify(content: str) -> str:
    """LLM 失败时的兜底分类。"""
    if not contains_japanese(content):
        return "not_japanese"
    if any(re.search(p, content) for p in _BLANK_PATTERNS):
        return "passage_with_blanks"
    if len(content) > 120 and ("。" in content or "\n" in content):
        return "passage_only"
    return "single_question"


def classify_content(content: str, call_llm) -> str:
    """LLM 分类；失败或误判（含日文却判非日语）时规则回退。"""
    qt = None
    try:
        raw = call_llm(build_classify_prompt(content), require_json=True)
        if raw:
            data = json.loads(_extract_json(raw))
            q = data.get("question_type", "")
            if q in VALID_TYPES:
                qt = q
    except Exception as e:
        print(f"[QA] 分类调用失败，使用规则回退: {e}")
    if qt is None:
        return rule_based_classify(content)
    # 防御：内容含日文字符却被判 not_japanese → 按规则重新判断
    if qt == "not_japanese" and contains_japanese(content):
        return rule_based_classify(content)
    return qt


# ---------- CC-1：解析缓存 ----------
def _cache_key(content: str, answer_key: str, user_answer: str, mode: str, detail: bool = False) -> str:
    """缓存键 = hash(题目 + 答案键 + 用户作答 + 模式 + 精/详档)。"""
    payload = json.dumps([content, answer_key, user_answer, mode, bool(detail)],
                         ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_cache() -> dict:
    if not os.path.exists(CACHE_FILE):
        return {"entries": {}}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"entries": {}}


def _save_cache(cache: dict) -> None:
    d = os.path.dirname(CACHE_FILE)
    if d and not os.path.exists(d):
        os.makedirs(d)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _cleanup_expired(cache: dict) -> dict:
    """清理 30 天前的冷数据（CC-1）。"""
    cutoff = datetime.now() - timedelta(days=CACHE_TTL_DAYS)
    keep = {}
    for k, entry in (cache.get("entries") or {}).items():
        try:
            created = datetime.fromisoformat(entry.get("created_at", ""))
            if created >= cutoff:
                keep[k] = entry
        except ValueError:
            keep[k] = entry
    cache["entries"] = keep
    return cache


def get_cached(key: str):
    entry = (_load_cache().get("entries") or {}).get(key)
    return entry.get("result") if entry else None


def put_cached(key: str, result: dict) -> None:
    cache = _cleanup_expired(_load_cache())
    cache["entries"][key] = {
        "result": result,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_cache(cache)


# ---------- 工具 ----------
def _extract_json(text: str) -> str:
    """剥离 ```json ... ``` 包裹（LLM 偶尔会加）。"""
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    return m.group(1).strip() if m else text


def _sanitize_sub_questions(raw) -> list:
    if not isinstance(raw, list):
        return []
    result = []
    for i, sq in enumerate(raw):
        if not isinstance(sq, dict):
            continue
        result.append({
            "id": sq.get("id", i + 1),
            "stem": str(sq.get("stem", "") or ""),
            "options": sq.get("options") or [],
            "answer": str(sq.get("answer", "") or ""),
        })
    return result


# ---------- QP-2/QP-6：解析组装 ----------
def _assemble_result(parsed: dict, mode: str, question_type: str,
                     answer_key: str, user_answer: str, detail: bool) -> dict:
    structure = parsed.get("structure") or {}
    ans = parsed.get("answer") or {}

    # QP-6：knowledge_tags 四层模型
    knowledge_tags = []
    for t in (parsed.get("knowledge_tags") or [])[:MAX_TAGS]:
        tag, typ = (t.get("tag"), t.get("type")) if isinstance(t, dict) else (str(t), "")
        tag = str(tag).strip()
        if not tag:
            continue
        if typ not in ("grammar", "vocab_pair", "comprehension"):
            typ = "comprehension"
        item = {"tag": tag, "type": typ}
        if mode == "C":  # ADR #7：AI 推断知识点，待确认池
            item["ai_inferred"] = True
        knowledge_tags.append(item)

    result = {
        "success": True,
        "mode": mode,
        "question_type": question_type,
        "ai_answered": mode == "C",
        "structure": {
            "stem": str(structure.get("stem", "") or ""),
            "options": structure.get("options") or [],
            "passage": structure.get("passage") or None,
            "sub_questions": _sanitize_sub_questions(structure.get("sub_questions")),
        },
        "answer": {
            "answer_key": answer_key,
            "user_answer": user_answer,
            "is_correct": None,
            "ai_solved": mode == "C",
            "correct_answer": ans.get("value", "") if mode in ("B", "C") else "",
            "ai_confidence": ans.get("confidence") if mode == "C" else None,
            "judgment": ans.get("judgment", "") if mode == "B" else "",
        },
        "explanation": str(parsed.get("explanation", "") or ""),
        "knowledge_tags": knowledge_tags,
        "parsed_at": datetime.now().isoformat(timespec="seconds"),
    }
    if detail:  # QP-7：详细版
        result["explanation_detail"] = str(parsed.get("explanation_detail", "") or "")

    # QP-3：模式 A 且提供了用户作答 → 确定性判分
    if mode == "A" and user_answer and user_answer.strip():
        result["answer"]["is_correct"] = deterministic_grade(user_answer, answer_key)["is_correct"]

    return result


# ---------- 主入口 ----------
def parse_question(content: str, answer_key: str = "", user_answer: str = "",
                   level: str = "N4", detail: bool = False, call_llm=None,
                   knowledge_context: str = "") -> dict:
    """解析一道题（或一段含多题的输入）。返回解析结果 dict。

    校验失败 / 非日语 → ValueError；LLM 失败 → RuntimeError。
    knowledge_context：TF-IDF 检索出的相关已学知识（CC-2），非空时拼入解析 prompt。
    """
    content = (content or "").strip()
    if not content:
        raise ValueError("题目内容不能为空")
    if len(content) > MAX_QA_LENGTH:
        raise ValueError(f"题目内容过长（最大 {MAX_QA_LENGTH} 字）")

    mode = detect_mode(answer_key, user_answer)
    key = _cache_key(content, answer_key, user_answer, mode, detail)

    # CC-1：缓存命中则零 token 返回
    cached = get_cached(key)
    if cached is not None:
        result = dict(cached)
        result["cached"] = True
        return result

    if call_llm is None:
        raise RuntimeError("未配置 LLM 调用函数")

    # QP-1：分类
    question_type = classify_content(content, call_llm)
    if question_type == "not_japanese":
        raise ValueError(
            "未检测到日语内容，请确认上传的是日语题目。"
            "示例：次の言葉を使って、正しい文を作りなさい。"
        )

    # 解析（单次 LLM 调用，多道小题由 LLM 拆入 sub_questions，CC-3 批量合并）
    prompt = build_parse_prompt(content, mode, answer_key, user_answer,
                                level, detail, question_type, knowledge_context)
    raw = call_llm(prompt, require_json=True)
    if not raw:
        raise RuntimeError("AI 服务调用失败，请检查 API Key 和网络连接")
    try:
        parsed = json.loads(_extract_json(raw))
    except json.JSONDecodeError:
        raise RuntimeError("AI 返回格式异常，请重试")

    result = _assemble_result(parsed, mode, question_type, answer_key, user_answer, detail)
    put_cached(key, result)
    result["cached"] = False
    return result
