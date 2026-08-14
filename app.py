"""
KOTOBA·AI — 日语语法闯关练习工具
Flask 后端入口

启动方式：python app.py
默认地址：http://127.0.0.1:5000
"""

import io
import sys


class _SafeStream:
    """永不抛编码异常的输出流包装。

    PyInstaller / MSIX 打包后 stdout/stderr 的编码跟随系统区域（美区为
    cp1252 / charmap），打印中文或日文字符会抛 UnicodeEncodeError（微软商店
    测试复现：'charmap' codec can't encode characters in position 6-9）。
    单靠 reconfigure() 在冻结环境下可能不生效（stdout 未必是可重配的标准
    TextIOWrapper），因此这里再包一层：文本先按 UTF-8 编码成字节写到底层
    buffer，任何失败都静默吞掉 —— print() 在任意环境下都不再崩溃（日志可能
    乱码，但绝不中断功能）。
    """

    def __init__(self, raw):
        self._raw = raw
        self._buffer = getattr(raw, "buffer", None) if raw is not None else None

    def write(self, s):
        if s is None:
            return 0
        if isinstance(s, bytes):
            s = s.decode("utf-8", "replace")
        try:
            if self._buffer is not None:
                self._buffer.write(s.encode("utf-8", "replace"))
            elif self._raw is not None:
                self._raw.write(s)
            return len(s)
        except Exception:
            return len(s)

    def flush(self):
        try:
            if self._raw is not None:
                self._raw.flush()
        except Exception:
            pass

    @property
    def buffer(self):
        return self._buffer

    @property
    def encoding(self):
        return "utf-8"

    @property
    def errors(self):
        return "replace"

    def isatty(self):
        return False

    def fileno(self):
        try:
            return self._raw.fileno() if self._raw is not None else -1
        except Exception:
            return -1

    @property
    def closed(self):
        return False

    def reconfigure(self, *args, **kwargs):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


# 先把真实流切到 UTF-8（有效时控制台/日志可读），再包一层 _SafeStream 兜底，
# 保证任何流（含 reconfigure 不生效的冻结环境）下 print 都不再抛编码异常。
for _name in ("stdout", "stderr"):
    _raw = getattr(sys, _name)
    if _raw is not None:
        try:
            _raw.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, io.UnsupportedOperation):
            pass
    setattr(sys, _name, _SafeStream(_raw))

import json
import os
from datetime import datetime, timedelta

import paths

from flask import Flask, jsonify, request, send_from_directory
from openai import OpenAI

from prompts.generate_questions import (
    build_generate_questions_prompt,
    build_essay_question_prompt,
)
from prompts.grade_answer import (
    build_grade_answer_prompt,
    build_regenerate_question_prompt,
    build_harder_question_prompt,
    build_essay_grade_prompt,
)
from prompts.generate_summary import build_generate_summary_prompt
from qa_pipeline import (
    parse_question,
    classify_content,
    detect_mode,
    MAX_QA_LENGTH as MAX_QA_CONTENT_LENGTH,
)
from knowledge_mapper import (
    collect_pending,
    confirm_pending,
    discard_pending,
    list_pending,
    reparse_pending,
    rebuild_index,
    retrieve_top_k,
    build_qa_knowledge_context,
)
# --- 初始化 ---
import sys

# PyInstaller 打包后资源路径处理
def resource_path(relative_path):
    """获取资源文件的绝对路径（兼容 PyInstaller 打包）。"""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

app = Flask(__name__, static_folder=resource_path("static"), static_url_path="")
# 限制请求体大小 11MB（M5：上传路由允许 10MB 文件 + 余量；文本接口在函数内自行校验长度）
app.config["MAX_CONTENT_LENGTH"] = 11 * 1024 * 1024

# 全局错误处理：所有异常都返回 JSON，避免前端收到 HTML 报错页
@app.errorhandler(Exception)
def handle_all_errors(e):
    from werkzeug.exceptions import HTTPException
    # 保留 HTTP 异常状态码（如 413 请求体过大），非 HTTP 异常统一 500
    status = e.code if isinstance(e, HTTPException) else 500
    if request.path.startswith("/api/"):
        # 兜底：任何残留的编码异常（charmap/cp1252 无法编码中文日文）都给用户
        # 友好提示，而不是把原始 Python 报错直接甩到界面上（商店测试策略 10.1.2.10）
        if isinstance(e, UnicodeEncodeError):
            return jsonify({"error": "服务器内部错误：输出编码异常，请重试"}), status
        return jsonify({"error": f"服务器内部错误：{str(e)}"}), status
    # 非 API 路由（如静态文件）使用默认 HTML 处理
    return str(e), status

# 启动时自动关闭占用同一端口的旧进程（方便更新版本）
import subprocess as _sp
def _kill_old_instance(port=5000):
    try:
        r = _sp.run(["netstat","-ano"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                pid = line.strip().split()[-1]
                if pid.isdigit():
                    _sp.run(["taskkill","/f","/pid",pid], capture_output=True, timeout=5)
    except Exception:
        pass
_kill_old_instance(5000)

# 输入验证常量
MAX_NOTES_LENGTH = 50000      # 笔记最多 5 万字
MAX_VOCAB_LENGTH = 20000      # 单词最多 2 万字
MAX_ANSWER_LENGTH = 10000     # 答案最多 1 万字
MAX_RECORDS_COUNT = 100       # 答题记录最多 100 条


# --- 工具函数 ---
def validate_input(value, max_len, field_name):
    """验证输入长度，超限返回错误信息。"""
    if value and len(value) > max_len:
        return f"{field_name}过长（最大 {max_len} 字）"
    return None

def sanitize_date(date_str):
    """验证日期格式为 YYYY-MM-DD，防止路径穿越。"""
    import re
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return None
    return date_str

def load_json(filepath, default=None):
    """安全加载 JSON 文件，文件不存在时返回默认值。"""
    filepath = paths.resolve(filepath)  # 统一数据目录
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
    filepath = paths.resolve(filepath)  # 统一数据目录
    dirname = os.path.dirname(filepath)
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_deepseek_client():
    """获取 DeepSeek API 客户端。
    优先使用环境变量 DEEPSEEK_API_KEY（生产环境），
    其次读取 config.json（本地开发）。"""
    # 优先读环境变量（服务器部署用）
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    model = os.environ.get("DEEPSEEK_MODEL", "")

    # 环境变量未设置时，回退到 config.json（本地开发用）
    if not api_key:
        config = load_json("config.json")
        api_key = config.get("api_key", "")
        if not model:
            model = config.get("model", "deepseek-chat")

    if not api_key:
        return None, "API Key 未设置"

    if not model:
        model = "deepseek-chat"

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    return client, model


def call_deepseek(prompt: str, require_json: bool = True) -> str:
    """
    调用 DeepSeek API，返回响应文本。
    失败时返回 None 并打印错误。
    """
    client, model = get_deepseek_client()
    if client is None:
        print("[错误] API Key 未设置，请先在界面中输入 DeepSeek API Key")
        return None

    print(f"[API] 正在调用 DeepSeek（模型: {model}）...")

    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    if require_json:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(**kwargs)
        print(f"[API] DeepSeek 返回成功")
        return response.choices[0].message.content
    except Exception as e:
        error_msg = str(e)
        print(f"[API 错误] {error_msg}")
        return None


# --- 静态文件 ---
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# --- 配置管理 ---
@app.route("/api/config", methods=["GET", "POST"])
def handle_config():
    if request.method == "GET":
        config = load_json("config.json")
        # 读取 API Key
        api_key = config.get("api_key", "")
        masked = ""
        if len(api_key) > 8:
            masked = api_key[:4] + "****" + api_key[-4:]
        model = os.environ.get("DEEPSEEK_MODEL", "") or config.get("model", "deepseek-chat")
        return jsonify({
            "api_key": api_key,
            "api_key_masked": masked,
            "has_api_key": bool(api_key),
            "level": config.get("level", "N4"),
            "model": model,
            "learning_goal": config.get("learning_goal", ""),
        })
    else:  # POST
        data = request.get_json(silent=True) or {}
        config = load_json("config.json")
        if "api_key" in data:
            config["api_key"] = data["api_key"]
        if "level" in data:
            config["level"] = data["level"]
        if "model" in data:
            config["model"] = data["model"]
        if "learning_goal" in data:
            config["learning_goal"] = data["learning_goal"]
        save_json("config.json", config)
        return jsonify({"success": True})


# --- 出题 ---
@app.route("/api/generate_questions", methods=["POST"])
def generate_questions():
    data = request.get_json(silent=True) or {}
    notes = data.get("notes", "").strip()
    level = data.get("level", "N4")
    vocab_text = data.get("vocabulary", "").strip()
    textbook_vocab = data.get("textbook_vocab", [])  # 教材单词
    question_type = data.get("question_type", "translation").strip()  # M4: 题型
    focus_tags = data.get("focus_tags", [])  # M4: 答疑联动知识点

    if not notes and not focus_tags:
        return jsonify({"error": "请提供语法笔记或选择语法点范围"}), 400

    # 校验题型参数（M4）
    VALID_QUESTION_TYPES = ("translation", "fill_blank", "mixed")
    if question_type not in VALID_QUESTION_TYPES:
        return jsonify({"error": f"题型参数无效，仅支持：{' / '.join(VALID_QUESTION_TYPES)}"}), 400

    # 输入长度验证
    err = validate_input(notes, MAX_NOTES_LENGTH, "笔记内容")
    if err: return jsonify({"error": err}), 400
    err = validate_input(vocab_text, MAX_VOCAB_LENGTH, "单词内容")
    if err: return jsonify({"error": err}), 400

    # 读取已学内容
    learned = load_json("learned_content.json")
    learned_items = learned.get("items", [])

    # 读取已学单词库
    vocab_bank = load_json("vocabulary.json")
    vocab_words = vocab_bank.get("words", [])

    prompt = build_generate_questions_prompt(
        notes, level, learned_items, vocab_text, vocab_words,
        textbook_vocab=textbook_vocab,
        question_type=question_type,
        focus_tags=focus_tags,
    )
    response_text = call_deepseek(prompt, require_json=True)

    if response_text is None:
        return jsonify({"error": "AI 服务调用失败，请检查 API Key 和网络连接"}), 500

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        # 有时 AI 返回的 JSON 被包裹在 ```json ... ``` 中
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response_text)
        if match:
            try:
                result = json.loads(match.group(1))
            except json.JSONDecodeError:
                return jsonify({"error": "AI 返回格式异常，请重试", "raw": response_text[:500]}), 500
        else:
            return jsonify({"error": "AI 返回格式异常，请重试", "raw": response_text[:500]}), 500

    # 更新 level 到配置
    config = load_json("config.json")
    config["level"] = level
    save_json("config.json", config)

    return jsonify({"success": True, "data": result})


# --- 终极挑战作文题 ---
@app.route("/api/generate_essay", methods=["POST"])
def generate_essay():
    data = request.get_json(silent=True) or {}
    grammar_points = data.get("grammar_points", [])
    level = data.get("level", "N4")
    notes = data.get("notes", "")

    if not grammar_points:
        return jsonify({"error": "没有语法点"}), 400

    # 读取单词库
    vocab_bank = load_json("vocabulary.json")
    vocab_words = vocab_bank.get("words", [])

    prompt = build_essay_question_prompt(grammar_points, level, notes, vocab_words)
    response_text = call_deepseek(prompt, require_json=True)

    if response_text is None:
        return jsonify({"error": "AI 服务调用失败"}), 500

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response_text)
        if match:
            try:
                result = json.loads(match.group(1))
            except json.JSONDecodeError:
                return jsonify({"error": "AI 返回格式异常"}), 500
        else:
            return jsonify({"error": "AI 返回格式异常"}), 500

    return jsonify({"success": True, "data": result})


# --- 作文批改 ---
@app.route("/api/grade_essay", methods=["POST"])
def grade_essay():
    data = request.get_json(silent=True) or {}
    essay_question = data.get("essay_question", {})
    user_answer = data.get("user_answer", "").strip()
    level = data.get("level", "N4")

    if not user_answer:
        return jsonify({"error": "答案不能为空"}), 400
    err = validate_input(user_answer, MAX_ANSWER_LENGTH * 3, "答案")
    if err: return jsonify({"error": err}), 400

    prompt = build_essay_grade_prompt(essay_question, user_answer, level)
    response_text = call_deepseek(prompt, require_json=True)

    if response_text is None:
        return jsonify({"error": "AI 服务调用失败"}), 500

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response_text)
        if match:
            try:
                result = json.loads(match.group(1))
            except json.JSONDecodeError:
                return jsonify({"error": "AI 返回格式异常"}), 500
        else:
            return jsonify({"error": "AI 返回格式异常"}), 500

    return jsonify({"success": True, "feedback": result})


# --- 批改 ---
@app.route("/api/grade_answer", methods=["POST"])
def grade_answer():
    data = request.get_json(silent=True) or {}
    question = data.get("question", {})
    user_answer = data.get("user_answer", "").strip()
    level = data.get("level", "N4")
    action = data.get("action", "grade")  # "grade" | "harder" | "retry"

    # --- 处理"换题重练"请求（不需要批改，直接生成新题）---
    if action == "retry":
        grammar_point = question.get("grammar_point", "")
        # 读取已学内容，限制新题只能组合已学语法
        learned = load_json("learned_content.json")
        learned_items = learned.get("items", [])
        prompt = build_regenerate_question_prompt(grammar_point, level, question, learned_items, question_type=question.get("question_type", "translation"))
        response_text = call_deepseek(prompt, require_json=True)
        if response_text is None:
            return jsonify({"error": "AI 服务调用失败"}), 500
        try:
            new_question = json.loads(response_text)
        except json.JSONDecodeError:
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response_text)
            if match:
                new_question = json.loads(match.group(1))
            else:
                return jsonify({"error": "生成新题失败，请重试"}), 500
        return jsonify({"success": True, "action": "retry", "new_question": new_question})

    # --- 处理"加大难度"请求（不需要批改，直接生成更难题目）---
    if action == "harder":
        grammar_point = question.get("grammar_point", "")
        current_diff = question.get("difficulty", 1)
        # 读取已学内容，限制进阶题只能组合已学语法
        learned = load_json("learned_content.json")
        learned_items = learned.get("items", [])
        prompt = build_harder_question_prompt(grammar_point, level, question, current_diff, learned_items, question_type=question.get("question_type", "translation"))
        response_text = call_deepseek(prompt, require_json=True)
        if response_text is None:
            return jsonify({"error": "AI 服务调用失败"}), 500
        try:
            new_question = json.loads(response_text)
        except json.JSONDecodeError:
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response_text)
            if match:
                new_question = json.loads(match.group(1))
            else:
                return jsonify({"error": "生成新题失败，请重试"}), 500
        return jsonify({"success": True, "action": "harder", "new_question": new_question})

    # --- 正常批改：必须有答案 ---
    if not user_answer:
        return jsonify({"error": "答案不能为空"}), 400
    err = validate_input(user_answer, MAX_ANSWER_LENGTH, "答案")
    if err: return jsonify({"error": err}), 400

    # --- 选择题（fill_blank）确定性判分：无需 LLM（M4）---
    if question.get("question_type") == "fill_blank":
        correct_option = question.get("correct_option", 0)
        stem = question.get("stem", "")
        explanation = question.get("explanation", "")
        options = question.get("options", [])
        option_labels = ["A", "B", "C", "D"]
        try:
            selected = int(user_answer)
        except (ValueError, TypeError):
            return jsonify({"error": "选择题答案必须是选项编号（0-3）"}), 400
        is_correct = (selected == correct_option)
        correct_text = options[correct_option] if 0 <= correct_option < len(options) else f"选项{correct_option}"
        selected_text = options[selected] if 0 <= selected < len(options) else f"选项{selected}"
        selected_label = option_labels[selected] if 0 <= selected < len(option_labels) else str(selected)
        correct_label = option_labels[correct_option] if 0 <= correct_option < len(option_labels) else str(correct_option)
        return jsonify({
            "success": True,
            "action": "grade",
            "feedback": {
                "is_correct": is_correct,
                "correct_option": correct_option,
                "selected_option": selected,
                "score": 10.0 if is_correct else 0.0,
                "correct_parts": ["✅ 回答正确！"] if is_correct else [],
                "error_parts": [] if is_correct else [
                    {
                        "level": "❌",
                        "error": f"你选择了 {selected_label}：{selected_text}",
                        "correction": f"正确答案是 {correct_label}：{correct_text}",
                        "explanation": explanation or "请查看题目解析",
                    }
                ],
                "suggestions": "",
                "encouragement": "答对了！继续加油💪" if is_correct else "别灰心，看看解析再试一次！💪",
                "deterministic": True,
                "no_llm": True,
            },
        })

    # 正常批改
    prompt = build_grade_answer_prompt(question, user_answer, level)
    response_text = call_deepseek(prompt, require_json=True)

    if response_text is None:
        return jsonify({"error": "AI 服务调用失败"}), 500

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response_text)
        if match:
            try:
                result = json.loads(match.group(1))
            except json.JSONDecodeError:
                return jsonify({"error": "AI 返回格式异常", "raw": response_text[:500]}), 500
        else:
            return jsonify({"error": "AI 返回格式异常", "raw": response_text[:500]}), 500

    return jsonify({
        "success": True,
        "action": "grade",
        "feedback": result,
    })


# --- 生成总结 ---
@app.route("/api/generate_summary", methods=["POST"])
def generate_summary():
    data = request.get_json(silent=True) or {}
    notes = data.get("notes", "")
    level = data.get("level", "N4")
    records = data.get("records", [])
    vocab_used = data.get("vocab_used", [])

    if not records:
        return jsonify({"error": "没有答题记录"}), 400
    if len(records) > MAX_RECORDS_COUNT:
        return jsonify({"error": "答题记录数异常"}), 400

    prompt = build_generate_summary_prompt(notes, level, records, vocab_used)
    response_text = call_deepseek(prompt, require_json=False)

    if response_text is None:
        return jsonify({"error": "AI 服务调用失败"}), 500

    # 保存 Markdown 文件
    today = datetime.now().strftime("%Y-%m-%d")
    md_filename = f"review_{today}.md"
    md_path = paths.data_path("output", md_filename)
    save_json(md_path.replace(".md", ".json"), {})  # 不适用，直接写 md
    dirname = os.path.dirname(md_path)
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(response_text)

    # 保存历史记录
    history_path = os.path.join("history", f"{today}.json")
    existing_history = load_json(history_path, {"records": []})
    existing_history["records"].extend(records)
    existing_history["summary_md"] = md_filename
    existing_history["level"] = level
    existing_history["updated_at"] = datetime.now().isoformat()
    save_json(history_path, existing_history)

    return jsonify({
        "success": True,
        "markdown": response_text,
        "filename": md_filename,
        "date": today,
    })


# --- 答疑（QA）M1：分类路由 + 三模式解析 + 缓存 ---
@app.route("/api/qa/classify", methods=["POST"])
def qa_classify():
    """QP-1：LLM 快速分类输入，返回 question_type 与模式。"""
    data = request.get_json(silent=True) or {}
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"error": "题目内容不能为空"}), 400
    err = validate_input(content, MAX_QA_CONTENT_LENGTH, "题目内容")
    if err: return jsonify({"error": err}), 400

    question_type = classify_content(content, call_deepseek)
    mode = detect_mode(data.get("answer_key", ""), data.get("user_answer", ""))
    resp = {"success": True, "question_type": question_type, "mode": mode}
    if question_type == "not_japanese":
        resp["warning"] = "未检测到日语内容，请确认上传的是日语题目（示例：次の言葉を使って文を作りなさい。）"
    return jsonify(resp)


@app.route("/api/qa/parse", methods=["POST"])
def qa_parse():
    """QP-2/QP-3/QP-6/CC-1：三模式解析，确定性判分，缓存命中零 token。
    M3：模式 C 知识点进待确认池（KB-3）；TF-IDF 相关知识拼入 prompt（KB-5/CC-2）。"""
    data = request.get_json(silent=True) or {}
    content = data.get("content", "")
    level = data.get("level", "N4")
    try:
        # KB-5/CC-2：检索相关已学知识作为参考上下文（辅助信息，不参与缓存键）
        knowledge_context = build_qa_knowledge_context(content, k=3)
        result = parse_question(
            content=content,
            answer_key=data.get("answer_key", ""),
            user_answer=data.get("user_answer", ""),
            level=level,
            detail=bool(data.get("detail", False)),
            call_llm=call_deepseek,
            knowledge_context=knowledge_context,
        )
        # KB-3：模式 C 的知识点进待确认池（重复内容自动去重）
        if result.get("mode") == "C" and not result.get("cached"):
            collect_pending(content, result, level=level)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


# --- 答疑（QA）M5：文件上传（PDF 文本提取 / 图片 OCR） ---
import PyPDF2
import io
from PIL import Image

ALLOWED_QA_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp"}
MAX_QA_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_QA_IMAGE_DIM = 4096  # 图片最长边上限，超出自动缩放（控制 OCR 耗时）
OCR_REC_MODEL = os.path.join("ocr_models", "japan_PP-OCRv4_rec_mobile.onnx")

# OCR 引擎单例（首次调用才加载，约 1-2 秒；后续请求复用）
_ocr_engine = None


def _get_ocr_engine():
    """懒加载 RapidOCR 引擎（日文识别模型）。失败返回 None 并记录。"""
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine = RapidOCR(rec_model_path=resource_path(OCR_REC_MODEL))
        except Exception as e:
            _ocr_engine = False  # 标记失败，避免每次重试
            print(f"[QA] OCR 引擎加载失败: {e}")
    return _ocr_engine if _ocr_engine else None


def ocr_process(image_bytes: bytes) -> str:
    """图片字节 → 日文 OCR → 文本（按行拼接）。RapidOCR 日本语识别模型。"""
    engine = _get_ocr_engine()
    if engine is None:
        raise RuntimeError("OCR 引擎不可用，请检查应用完整性")
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        raise ValueError("无法识别该图片格式，请上传 PNG / JPG / WebP 图片")
    w, h = img.size
    if max(w, h) > MAX_QA_IMAGE_DIM:  # 超大图等比缩放
        scale = MAX_QA_IMAGE_DIM / max(w, h)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    res, _ = engine(buf.getvalue())
    lines = []
    for item in res or []:
        txt = item[1]
        if txt and str(txt).strip():
            lines.append(str(txt).strip())
    return "\n".join(lines)


@app.route("/api/qa/upload", methods=["POST"])
def qa_upload():
    """接收 PDF / 图片，提取文本返回。PDF 走 PyPDF2 文本提取，图片走日文 OCR。"""
    if "file" not in request.files:
        return jsonify({"error": "未选择文件"}), 400

    file = request.files["file"]
    if not file.filename or file.filename == "":
        return jsonify({"error": "未选择文件"}), 400

    # 扩展名校验
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_QA_EXTENSIONS:
        return jsonify({"error": f"暂不支持 .{ext} 格式，请上传 PDF 或图片（PNG/JPG/WebP）"}), 400

    # 大小校验
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_QA_FILE_SIZE:
        return jsonify({"error": f"文件过大（最大 10 MB，当前 {size // 1024 // 1024} MB）"}), 400
    if size == 0:
        return jsonify({"error": "文件为空，请重新选择"}), 400

    if ext == "pdf":
        # PDF 文本提取
        try:
            pdf_bytes = file.read()
            reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        except Exception as e:
            return jsonify({"error": f"无法读取 PDF 文件：{str(e)}"}), 400

        pages_text = []
        total_pages = len(reader.pages)
        if total_pages > 50:
            return jsonify({"error": f"PDF 页数过多（最大 50 页，当前 {total_pages} 页）"}), 400

        for i, page in enumerate(reader.pages):
            try:
                text = page.extract_text()
                if text and text.strip():
                    pages_text.append(text.strip())
            except Exception:
                pages_text.append(f"[第 {i+1} 页提取失败]")

        extracted = "\n\n".join(pages_text).strip()

        if not extracted or len(extracted) < 10:
            return jsonify({
                "success": False,
                "warning": "未能提取到足够文字。这份 PDF 可能是扫描件（图片型），请使用「图片」入口识别，或「文字」入口手动粘贴。",
            })
        pages = total_pages
    else:
        # 图片 → OCR
        image_bytes = file.read()
        try:
            extracted = ocr_process(image_bytes)
        except ValueError as e:
            return jsonify({"success": False, "warning": str(e)}), 400
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 500
        if not extracted or len(extracted) < 10:
            return jsonify({
                "success": False,
                "warning": "未能识别到足够文字。请确保图片清晰、包含日语文字，或使用「文字」入口手动粘贴。",
            })
        pages = 1

    if len(extracted) > MAX_QA_CONTENT_LENGTH:
        extracted = extracted[:MAX_QA_CONTENT_LENGTH] + "\n\n[内容已截断，超过单次答疑上限]"

    return jsonify({
        "success": True,
        "text": extracted,
        "pages": pages,
        "ext": ext,
        "size": size,
    })



# --- 答疑（QA）M3：待确认池（KB-3/KB-4） + 知识检索（KB-5） ---
@app.route("/api/qa/pending", methods=["GET"])
def qa_pending_list():
    """KB-3：列出待确认池。"""
    items = list_pending()
    return jsonify({"items": items, "count": len(items)})


@app.route("/api/qa/pending/confirm", methods=["POST"])
def qa_pending_confirm():
    """KB-3：确认知识点 → 映射去重入库 learned_content。"""
    data = request.get_json(silent=True) or {}
    try:
        result = confirm_pending(data.get("ids", []))
        return jsonify({"success": True, **result})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/qa/pending/discard", methods=["POST"])
def qa_pending_discard():
    """KB-3：丢弃待确认条目。"""
    data = request.get_json(silent=True) or {}
    try:
        n = discard_pending(data.get("ids", []))
        return jsonify({"success": True, "discarded": n})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/qa/pending/reparse", methods=["POST"])
def qa_pending_reparse():
    """KB-4：补充答案键后整题重新解析，覆盖 AI 推断。"""
    data = request.get_json(silent=True) or {}
    try:
        res = reparse_pending(
            item_id=data.get("id", ""),
            answer_key=data.get("answer_key", ""),
            level=data.get("level", "N4"),
            call_llm=call_deepseek,
        )
        return jsonify({"success": True, "item": res["item"], "result": res["result"]})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/knowledge/retrieve", methods=["GET"])
def knowledge_retrieve():
    """KB-5：TF-IDF 检索相关知识 top-k。"""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "检索词不能为空"}), 400
    k = request.args.get("k", 3, type=int)
    k = min(max(k, 1), 10)
    return jsonify({"success": True, "query": q, "results": retrieve_top_k(q, k=k)})


@app.route("/api/knowledge/rebuild_index", methods=["POST"])
def knowledge_rebuild_index():
    """KB-5：重建 TF-IDF 索引。"""
    n = rebuild_index()
    index = load_json("knowledge_index.json")
    return jsonify({"success": True, "corpus_size": n, "built_at": index.get("built_at", "")})


# --- 进度管理 ---
@app.route("/api/progress", methods=["GET", "POST", "DELETE"])
def handle_progress():
    if request.method == "GET":
        progress = load_json("progress.json", None)
        if progress and progress.get("current_index") is not None:
            return jsonify({"has_progress": True, "data": progress})
        return jsonify({"has_progress": False, "data": None})

    elif request.method == "POST":
        data = request.get_json(silent=True) or {}
        save_json("progress.json", data)
        return jsonify({"success": True})

    elif request.method == "DELETE":
        progress_path = paths.data_path("progress.json")
        if os.path.exists(progress_path):
            os.remove(progress_path)
        return jsonify({"success": True})


# --- 已学内容管理 ---
@app.route("/api/learned_content", methods=["GET", "POST"])
def handle_learned_content():
    if request.method == "GET":
        learned = load_json("learned_content.json")
        return jsonify(learned)

    elif request.method == "POST":
        data = request.get_json(silent=True) or {}
        new_items = data.get("items", [])
        if not new_items:
            return jsonify({"error": "没有要更新的内容"}), 400

        learned = load_json("learned_content.json")
        existing = learned.get("items", [])

        # 合并更新
        existing_map = {item["grammar_point"]: item for item in existing}
        today = datetime.now().strftime("%Y-%m-%d")

        for new_item in new_items:
            gp = new_item.get("grammar_point", "")
            new_score = new_item.get("score", 0)
            if gp in existing_map:
                old = existing_map[gp]
                old_reviews = old.get("review_count", 0)
                old_mastery = old.get("mastery", 0)
                # 新掌握度 = (旧掌握度 * 旧次数 + 本次得分/10) / (旧次数 + 1)
                new_mastery = (old_mastery * old_reviews + new_score / 10) / (old_reviews + 1)
                old["mastery"] = round(new_mastery, 2)
                old["review_count"] = old_reviews + 1
                old["last_reviewed"] = today
                if new_item.get("level"):
                    old["level"] = new_item["level"]

                # --- 艾宾浩斯 SM-2 调度 ---
                quality = min(5, max(0, int(new_score / 2)))  # 0-10 → 0-5
                old_stage = old.get("review_stage", 0)
                history = old.get("history_scores", [])
                history.append(new_score)
                old["history_scores"] = history[-10:]  # 保留最近10次

                intervals = [1, 2, 4, 7, 15, 30]
                if quality >= 3:
                    # 答对：推进阶段
                    new_stage = min(old_stage + 1, len(intervals) - 1)
                else:
                    # 答错：回退一个阶段
                    new_stage = max(0, old_stage - 1)

                old["review_stage"] = new_stage
                old["review_interval"] = intervals[new_stage]

                # 计算下次复习日期
                from datetime import date, timedelta
                next_date = date.today() + timedelta(days=intervals[new_stage])
                old["next_review"] = next_date.isoformat()
            else:
                new_item["first_learned"] = today
                new_item["last_reviewed"] = today
                new_item["review_count"] = 1
                new_item["mastery"] = round(new_score / 10, 2)
                # 初始化复习字段
                new_item["review_stage"] = 0
                new_item["review_interval"] = 1
                new_item["history_scores"] = [new_score]
                from datetime import date, timedelta
                new_item["next_review"] = (date.today() + timedelta(days=1)).isoformat()
                existing_map[gp] = new_item

        learned["items"] = list(existing_map.values())
        save_json("learned_content.json", learned)

        return jsonify({"success": True, "count": len(learned["items"])})


# --- 复习到期检测 ---
@app.route("/api/review_due", methods=["GET"])
def get_review_due():
    """返回今日到期的复习语法点。"""
    learned = load_json("learned_content.json")
    items = learned.get("items", [])
    today = datetime.now().strftime("%Y-%m-%d")

    due = [item for item in items if item.get("next_review", "2099-12-31") <= today]
    # 按掌握度从低到高排序，薄弱点优先复习
    due.sort(key=lambda x: x.get("mastery", 1.0))

    return jsonify({"due": due, "total": len(items)})


# --- 单词库管理 ---
@app.route("/api/vocabulary", methods=["GET", "POST"])
def handle_vocabulary():
    if request.method == "GET":
        vocab = load_json("vocabulary.json")
        return jsonify(vocab)

    elif request.method == "POST":
        data = request.get_json(silent=True) or {}
        new_words = data.get("words", [])
        if not new_words:
            return jsonify({"error": "没有要更新的单词"}), 400

        vocab = load_json("vocabulary.json")
        existing = vocab.get("words", [])

        # 按 "日语写法" 去重合并
        existing_map = {w["word"]: w for w in existing}
        today = datetime.now().strftime("%Y-%m-%d")

        for new_word in new_words:
            w = new_word.get("word", "").strip()
            if not w:
                continue
            if w in existing_map:
                old = existing_map[w]
                old_reviews = old.get("review_count", 0)
                old["review_count"] = old_reviews + 1
                old["last_reviewed"] = today
                if new_word.get("reading"):
                    old["reading"] = new_word["reading"]
                if new_word.get("meaning"):
                    old["meaning"] = new_word["meaning"]
                if new_word.get("pos"):
                    old["pos"] = new_word["pos"]
            else:
                new_word["first_learned"] = today
                new_word["last_reviewed"] = today
                new_word["review_count"] = 1
                existing_map[w] = new_word

        vocab["words"] = list(existing_map.values())
        save_json("vocabulary.json", vocab)

        return jsonify({"success": True, "count": len(vocab["words"])})


# --- 教材知识库 ---
@app.route("/api/knowledge_base", methods=["GET"])
def list_textbooks():
    """返回教材列表和课程索引。"""
    # 内置教材走 resource_path：PyInstaller 打包后位于 _MEIPASS，不能用相对 cwd 路径
    index = load_json(resource_path("knowledge_base/index.json"))
    return jsonify(index)


@app.route("/api/knowledge_base/<volume_id>", methods=["GET"])
def get_textbook_volume(volume_id):
    """加载指定教材分册的全部课程数据。"""
    index = load_json(resource_path("knowledge_base/index.json"))
    file_path = None
    for textbook in index.get("textbooks", []):
        for vol in textbook.get("volumes", []):
            if vol["id"] == volume_id:
                file_path = vol["file"]
                break

    if not file_path:
        return jsonify({"error": "教材不存在"}), 404

    full_path = os.path.join(resource_path("knowledge_base"), file_path)
    data = load_json(full_path, None)
    if data is None:
        return jsonify({"error": "教材文件不存在或格式错误"}), 404
    return jsonify(data)


# --- 错题本 ---
@app.route("/api/wrong_book", methods=["GET"])
def list_wrong_book():
    """获取错题本全部条目。"""
    wb = load_json("wrong_book.json")
    items = wb.get("items", [])
    # 按添加时间倒序，未掌握的排前面
    items.sort(key=lambda x: (x.get("mastered", False), x.get("added_at", "")), reverse=False)
    return jsonify({"items": items})


@app.route("/api/wrong_book", methods=["POST"])
def update_wrong_book():
    """新增或更新错题条目。"""
    data = request.get_json(silent=True) or {}
    new_items = data.get("items", [])
    if not new_items:
        return jsonify({"error": "没有要更新的内容"}), 400

    wb = load_json("wrong_book.json")
    existing = wb.get("items", [])
    existing_map = {item.get("id"): item for item in existing}

    for new_item in new_items:
        item_id = new_item.get("id")
        if item_id in existing_map:
            # 更新已有条目
            old = existing_map[item_id]
            old["reviewed_count"] = new_item.get("reviewed_count", old.get("reviewed_count", 0))
            old["last_reviewed"] = new_item.get("last_reviewed", old.get("last_reviewed"))
            old["score"] = new_item.get("score", old.get("score", 0))
            old["mastered"] = new_item.get("mastered", old.get("mastered", False))
        else:
            existing_map[item_id] = new_item

    wb["items"] = list(existing_map.values())
    save_json("wrong_book.json", wb)
    return jsonify({"success": True, "count": len(wb["items"])})


@app.route("/api/wrong_book/<int:item_id>", methods=["DELETE"])
def delete_wrong_item(item_id):
    """删除某个错题条目（标记为已掌握时调用）。"""
    wb = load_json("wrong_book.json")
    items = wb.get("items", [])
    wb["items"] = [i for i in items if i.get("id") != item_id]
    save_json("wrong_book.json", wb)
    return jsonify({"success": True})


# --- 重置所有数据 ---
@app.route("/api/reset", methods=["POST"])
def reset_all_data():
    """清空数据目录下全部本地数据并重置为默认状态。"""
    import shutil
    data_dir = paths.get_data_dir()
    cleared = 0
    if os.path.isdir(data_dir):
        for name in os.listdir(data_dir):
            p = os.path.join(data_dir, name)
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)
                cleared += 1
            except OSError:
                pass
    # 重建 config.json 为空配置
    save_json("config.json", {"api_key": "", "level": "N3", "model": "deepseek-chat"})
    return jsonify({"success": True, "cleared": cleared})


# --- 学习数据导出 / 导入（版本更新迁移不丢失数据） ---

def _collect_user_data():
    """收集除 API Key 外的全部用户学习数据。"""
    cfg = load_json("config.json", {})
    return {
        "app": "KOTOBA-AI",
        "export_version": 1,
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config": {k: v for k, v in cfg.items() if k != "api_key"},
        "progress": load_json("progress.json"),
        "learned_content": load_json("learned_content.json"),
        "wrong_book": load_json("wrong_book.json"),
        "vocabulary": load_json("vocabulary.json"),
        "pending_knowledge": load_json("pending_knowledge.json"),
        "qa_cache": load_json("cache/qa_cache.json"),
        "history": {
            f[:-5]: load_json(os.path.join("history", f))
            for f in sorted(os.listdir(paths.data_path("history")))
            if f.endswith(".json")
        } if os.path.exists(paths.data_path("history")) else {},
    }


@app.route("/api/data/export", methods=["GET"])
def export_user_data():
    """导出用户学习数据为 JSON 文件下载（不含 API Key）。"""
    payload = _collect_user_data()
    filename = f"kotoba_learning_data_{datetime.now().strftime('%Y%m%d')}.json"
    tmp_path = os.path.join("output", filename)
    save_json(tmp_path, payload)
    # 用绝对路径：PyInstaller 打包后 app.root_path 指向 _MEIPASS 临时目录，
    # 相对 "output" 会被解析到 _MEIPASS 下导致 NotFound，绝对路径不受影响。
    return send_from_directory(
        paths.data_path("output"), filename, as_attachment=True, download_name=filename
    )


@app.route("/api/data/import", methods=["POST"])
def import_user_data():
    """从导出的 JSON 备份恢复学习数据（合并 config，其余同名覆盖）。"""
    import re
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get("app") != "KOTOBA-AI":
        return jsonify({"error": "导入文件格式不正确，请使用 KOTOBA·AI 导出的备份文件"}), 400

    # config：保留现有 api_key，合并其余字段
    current_cfg = load_json("config.json", {})
    imported_cfg = data.get("config") or {}
    for k, v in imported_cfg.items():
        if k != "api_key":
            current_cfg[k] = v
    save_json("config.json", current_cfg)

    # 其余数据文件：同名覆盖
    file_mapping = [
        ("progress", "progress.json"),
        ("learned_content", "learned_content.json"),
        ("wrong_book", "wrong_book.json"),
        ("vocabulary", "vocabulary.json"),
        ("pending_knowledge", "pending_knowledge.json"),
        ("qa_cache", "cache/qa_cache.json"),
    ]
    for key, filepath in file_mapping:
        val = data.get(key)
        if isinstance(val, dict):
            save_json(filepath, val)

    # 历史记录：按日期合并（同名日期覆盖）
    history = data.get("history") or {}
    if isinstance(history, dict):
        for date_str, h in history.items():
            if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str) and isinstance(h, dict):
                save_json(os.path.join("history", f"{date_str}.json"), h)

    return jsonify({"success": True, "message": "学习数据导入成功"})


# --- 数据目录管理（统一存储） ---
@app.route("/api/data_dir", methods=["GET"])
def data_dir_info():
    """返回当前数据目录信息（设置页展示 + 前端判断是否已自定义）。"""
    return jsonify({"success": True, **paths.get_data_dir_info()})


@app.route("/api/data_dir/open", methods=["POST"])
def data_dir_open():
    """在文件管理器中打开当前数据目录。"""
    try:
        os.startfile(paths.get_data_dir())
        return jsonify({"success": True})
    except OSError as e:
        return jsonify({"error": f"无法打开数据目录：{e}"}), 500


@app.route("/api/data_dir/change", methods=["POST"])
def data_dir_change():
    """更改数据目录：迁移旧数据到新目录 → 写指针 → 延迟重启应用生效。"""
    data = request.get_json(silent=True) or {}
    new_dir = data.get("path", "").strip()
    if not new_dir:
        return jsonify({"error": "请选择数据目录"}), 400
    try:
        migrated = paths.set_data_dir(new_dir)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    # 延迟重启，让前端先渲染「迁移完成，即将重启」的提示
    from threading import Timer
    Timer(2.0, restart_app).start()
    return jsonify({"success": True, "migrated": migrated})


def restart_app():
    """重启应用（更换数据目录后生效）。frozen 下重启 exe，开发模式重启 python app.py。"""
    import subprocess
    try:
        if hasattr(sys, "_MEIPASS"):
            args = [sys.executable]
        else:
            args = [sys.executable, os.path.abspath(__file__)]
        subprocess.Popen(args, close_fds=True)
    except Exception as e:
        print(f"[重启失败] {e}")
        return
    os._exit(0)


@app.route("/api/shutdown", methods=["POST"])
def shutdown():
    """前端关闭页面时调用，立即退出进程。"""
    os._exit(0)


# --- 历史记录 ---
@app.route("/api/history", methods=["GET"])
def list_history():
    history_dir = paths.data_path("history")
    if not os.path.exists(history_dir):
        return jsonify({"files": []})

    files = []
    for f in sorted(os.listdir(history_dir), reverse=True):
        if f.endswith(".json"):
            filepath = os.path.join(history_dir, f)
            h = load_json(filepath)
            date_str = f.replace(".json", "")
            files.append({
                "date": date_str,
                "level": h.get("level", ""),
                "record_count": len(h.get("records", [])),
                "summary_md": h.get("summary_md", ""),
            })
    return jsonify({"files": files})


@app.route("/api/history/<date>", methods=["GET"])
def get_history_detail(date):
    date = sanitize_date(date)
    if not date:
        return jsonify({"error": "日期格式无效"}), 400
    filepath = os.path.join("history", f"{date}.json")
    data = load_json(filepath, None)
    if data is None:
        return jsonify({"error": "记录不存在"}), 404
    return jsonify({"success": True, "data": data})


@app.route("/api/download/<date>", methods=["GET"])
def download_markdown(date):
    """下载复习笔记 Markdown 文件。"""
    date = sanitize_date(date)
    if not date:
        return jsonify({"error": "日期格式无效"}), 400
    md_filename = f"review_{date}.md"
    md_path = paths.data_path("output", md_filename)
    if not os.path.exists(md_path):
        # 尝试从 history 中找到对应的 md 文件名
        history_path = paths.data_path("history", f"{date}.json")
        history = load_json(history_path, None)
        if history and history.get("summary_md"):
            md_filename = history["summary_md"]
            md_path = paths.data_path("output", md_filename)

    if not os.path.exists(md_path):
        return jsonify({"error": "文件不存在"}), 404

    # 用绝对路径：PyInstaller 打包后 app.root_path 指向 _MEIPASS，相对目录会解析到临时目录导致 NotFound
    return send_from_directory(
        paths.data_path("output"),
        md_filename,
        as_attachment=True,
        download_name=md_filename,
    )


@app.route("/api/checkin", methods=["GET"])
def get_checkin():
    """返回打卡数据：活跃日期列表、连续天数、本月天数。"""
    history_dir = paths.data_path("history")
    if not os.path.exists(history_dir):
        return jsonify({"dates": [], "streak": 0, "monthly_count": 0, "monthly_dates": []})

    dates = []
    for f in os.listdir(history_dir):
        if f.endswith(".json"):
            date_str = f.replace(".json", "")
            if len(date_str) == 10:  # YYYY-MM-DD
                dates.append(date_str)

    dates.sort()
    date_set = set(dates)

    # 计算连续打卡天数（从今天往前数）
    streak = 0
    check = datetime.now()
    # 如果今天还没打卡，从昨天开始算
    if datetime.now().strftime("%Y-%m-%d") not in date_set:
        check = datetime.now() - timedelta(days=1)

    while check.strftime("%Y-%m-%d") in date_set:
        streak += 1
        check = check - timedelta(days=1)

    # 本月打卡天数
    current_month = datetime.now().strftime("%Y-%m")
    monthly_dates = [d for d in dates if d.startswith(current_month)]

    return jsonify({
        "dates": dates,
        "streak": streak,
        "monthly_count": len(monthly_dates),
        "monthly_dates": monthly_dates,
    })


# --- 启动 ---
if __name__ == "__main__":
    from threading import Timer
    import webview

    # 首次启动：若数据目录为空，把 cwd 遗留旧数据复制进去（复制不移动，幂等安全）
    _migrated = paths.migrate_legacy_data()
    if _migrated:
        print(f"[数据迁移] 已从旧位置复制 {_migrated} 个文件到 {paths.get_data_dir()}")

    class JsApi:
        """暴露给前端 window.pywebview.api 的原生方法。"""
        def export_user_data_native(self):
            """弹出系统保存对话框，让用户选择导出位置后写入备份文件。"""
            try:
                payload = _collect_user_data()
                default_name = f"kotoba_learning_data_{datetime.now().strftime('%Y%m%d')}.json"
                result = webview.windows[0].create_file_dialog(
                    webview.SAVE_DIALOG,
                    save_filename=default_name,
                )
                if not result:
                    return {"cancelled": True}
                path = result if isinstance(result, str) else result[0]
                if not path.lower().endswith(".json"):
                    path += ".json"
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                return {"success": True, "path": path}
            except Exception as e:
                return {"success": False, "error": str(e)}

        def choose_data_dir(self):
            """弹出系统文件夹选择对话框，返回所选路径（取消返回 cancelled）。"""
            try:
                result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
                if not result:
                    return {"cancelled": True}
                path = result if isinstance(result, str) else result[0]
                return {"success": True, "path": path}
            except Exception as e:
                return {"success": False, "error": str(e)}

        def open_data_dir(self):
            """在文件管理器中打开当前数据目录。"""
            try:
                os.startfile(paths.get_data_dir())
                return {"success": True}
            except Exception as e:
                return {"success": False, "error": str(e)}

    def start_flask():
        app.run(host="127.0.0.1", port=5000, debug=False)

    Timer(0.5, start_flask).start()
    webview.create_window("KOTOBA·AI 言葉", "http://127.0.0.1:5000",
                          width=1200, height=800, min_size=(900, 600),
                          resizable=True, js_api=JsApi())
    webview.start()
