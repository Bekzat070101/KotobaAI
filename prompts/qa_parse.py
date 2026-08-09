"""
答疑（Q&A）Prompt 构建模块 — M1

QP-1 分类 prompt + QP-2 三模式（A/B/C）解析 prompt，QP-7 精简/详细两档。
判分（QP-3）在 qa_pipeline 中确定性完成，本模块不做判分。
"""

# 合法分类值（QP-1）
VALID_TYPES = ("single_question", "passage_with_blanks", "passage_only", "not_japanese")


def build_classify_prompt(content: str) -> str:
    """QP-1：输入 → LLM 快速分类，非日语被拦截。"""
    return f"""你是一个日语题目分类器。请判断下面的日语题目内容属于哪一类，只输出 JSON。

四类：
- single_question：单选/多选/单个问句/简答题（题干简短，可能有选项）
- passage_with_blanks：完形填空或含挖空的段落（用 ＿＿＿、（　）、【　】、___ 等表示空格）
- passage_only：整段文章/阅读理解（无挖空，可能有若干小题，或整篇待解）
- not_japanese：内容不含日语（如纯中文、英文或其他语言的题目），或根本不是题目

## 输入内容
{content}

## 输出（只返回 JSON，不要 Markdown 代码块）
{{"question_type": "single_question 或 passage_with_blanks 或 passage_only 或 not_japanese", "reason": "一句话分类理由"}}
"""


def build_parse_prompt(
    content: str,
    mode: str,
    answer_key: str,
    user_answer: str,
    level: str,
    detail: bool,
    question_type: str,
    knowledge_context: str = "",
) -> str:
    """QP-2/QP-6/QP-7：按模式 A/B/C 构建解析 prompt。

    mode A：有答案键（判分由系统确定性完成，LLM 不判对错）
    mode B：有用户作答（AI 评判）
    mode C：纯题目（AI 解题，低置信，标注🤖）
    knowledge_context：TF-IDF 检索出的相关已学知识（CC-2 上下文裁剪），非空时插入。
    """
    if mode == "A":
        mode_note = (
            "## 模式 A：有官方答案键\n"
            f"题目附带答案键（官方标准答案）：\n{answer_key}\n"
            "- 判分由系统用确定性对比完成，**你绝对不判对错**\n"
            "- 你的任务：解析题目结构、给出讲解、提取知识点\n"
            "- answer.value 留空字符串\n"
        )
    elif mode == "B":
        mode_note = (
            "## 模式 B：有用户作答，无答案键\n"
            f"用户作答：\n{user_answer}\n"
            "- 请评判该作答（judgment 填：正确 / 错误 / 部分正确，并说明原因）\n"
            "- answer.value 填正确说法或订正后的答案\n"
        )
    else:  # mode C
        mode_note = (
            "## 模式 C：纯题目，无答案\n"
            "- 请你亲自解题：answer.value 填你的答案\n"
            "- confidence 填你对答案的确信度（0-1，没把握给低分）\n"
            "- 本结果会标注 🤖 AI 解题\n"
        )

    # QP-7：详细版才要求输出逐句翻译 + 拆解
    detail_field = ""
    if detail:
        detail_field = '"explanation_detail": "逐句翻译 + 语法拆解（详细版，可写 2~4 句）",'

    # CC-2：相关已学知识（TF-IDF top-3），非空时作为参考上下文插入
    knowledge_section = ""
    if knowledge_context.strip():
        knowledge_section = f"\n{knowledge_context.strip()}\n"

    prompt = f"""你是一位精通日语的资深教师，正在帮助{level}级别学习者解析一道日语题。
{knowledge_section}## 输入内容
{content}

{mode_note}

## 任务
1. 解析题目结构（题干 / 选项 / 文章 / 子题）。如果内容包含多道独立小题，全部放入 sub_questions。
2. 给出讲解 explanation。
3. 提取 knowledge_tags 知识点（四层模型）：
   - grammar：可结构化的语法点（如 〜てから、～ようになる）
   - vocab_pair：易混词对（如 招く vs 呼ぶ），tag 写"词1 vs 词2"
   - comprehension：理解类（阅读主旨、作者意图、语境判断）
   - 实在没有知识点时 knowledge_tags 返回空数组（合法）
4. 按模式说明填写 answer。

## 输出（只返回 JSON，不要 Markdown 代码块）
{{
  "structure": {{
    "stem": "题干文本（无则空串）",
    "options": ["选项A", "选项B"],
    "passage": "完形/阅读全文；非段落题填 null",
    "sub_questions": [
      {{"id": 1, "stem": "小题题干或挖空位置", "options": [], "answer": "该小题答案"}}
    ]
  }},
  "answer": {{
    "value": "见模式说明",
    "confidence": 0.0,
    "judgment": "见模式说明"
  }},
  "explanation": "一句话讲解（不超过 60 字）",
  {detail_field}
  "knowledge_tags": [
    {{"tag": "知识点名称", "type": "grammar 或 vocab_pair 或 comprehension"}}
  ]
}}
"""
    return prompt
