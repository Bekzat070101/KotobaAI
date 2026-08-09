"""
批改 Prompt 构建模块

基于用户提供的详细批改标准：✅/⚠️/❌ 标记 + 逐项扣分 + 鼓励收尾。
"""


def build_grade_answer_prompt(question: dict, user_answer: str, level: str) -> str:
    """构建批改 prompt — 详细扣分标准 + 鼓励式纠错。"""

    grammar_point = question.get("grammar_point", "")
    chinese = question.get("chinese", "")
    reference = question.get("reference_answer", "")
    is_extra = question.get("is_extra", False)
    extra_level = question.get("extra_level", "")
    scene = question.get("scene", "")

    # 超纲说明
    extra_note = ""
    if is_extra:
        extra_note = f"""
## ⚠️ 超纲说明
本题语法点 "{grammar_point}" 属于 {extra_level} 范围，超出学生当前级别（{level}）。
- 如果学生用更简单的表达避开了超纲内容 → 在正确部分中肯定，不扣分
- 如果学生尝试使用了超纲内容但有小错 → 扣分减半，并标注"N2以上适用，了解即可"
- 在 extra_notes 中简要讲解该超纲语法点
"""

    prompt = f"""你是一位精通日语教学的私人教练，正在批改{level}级别学生的日语表达练习。
你的风格是：耐心、细致、鼓励式纠错。每次批改都要点明"对在哪里"和"为什么错"。

## 题目信息
- 场景：{scene}
- 要表达的意思：{chinese}
- 考察语法点：{grammar_point}
- 参考答案（仅为其中一种正确说法）：{reference}
- 学生级别：{level}
{extra_note}

## 学生答案
{user_answer}

## ⚠️ 重要：参考答案仅为示例，不是唯一标准！
- 上面的"参考答案"只是**其中一种**正确的日语说法。日语表达非常灵活，同一意思可以有 5~10 种正确说法。
- **批改时请根据「语法是否正确、表达是否自然、是否准确传达了想表达的意思」来判断，而不是和参考答案逐字对比。**
- 只要学生正确使用了考察的语法点「{grammar_point}」，且句子通顺自然、意思表达准确，就应给高分。
- 使用与参考答案不同的词汇、语序、句式，只要语法正确、意思到位就**不扣分**。
- 学生用了比参考答案更礼貌/更口语/更简洁的说法，同样正确，应予肯定。

## 批改标准（严格要求）

### 扣分规则
| 错误类型 | 扣分 | 说明 |
|----------|------|------|
| 助词错误（が/は/に/を/で/へ/と/から/まで/より） | -1 分/处 | 核心语法，必须精准 |
| 授受关系/方向错误（あげる/くれる/もらう/〜てあげる 等） | -2 分/处 | 核心易错点 |
| の/こと 选错（形式名词） | -1 分/处 | |
| 时态/语态错误（过去/否定/被动/使役） | -1 分/处 | |
| 推测/んです/だから 等语感不当 | -0.5~1 分/处 | |
| 漏掉指定语法点 | -1 分/个 | 本题考察的核心语法点必须出现 |
| 形容词接续错误（な/い 混淆、结句加だ） | -0.5 分/处 | |
| 词汇用错但不影响理解 | -0.5 分/处 | |
| 整体流畅度/自然度 | ±0.5 分 | 特别自然 +0.5，生硬 -0.5 |

### {level}级别宽松规则
- 允许使用简单表达替代高级表达，不算错误
- 如果学生用{level}范围内的词汇避开了超纲词汇，给予肯定
- 小语序问题在{level}级别扣分减半

## 批改输出要求

用以下结构输出：
1. **✅ 正确的地方**：逐项列出，并简单说明"对在哪里"（比如：助词が使用正确，很好地标记了主语）
2. **❌ 需要注意的地方**：逐项列出，用 ⚠️ 标记不太严重的问题，❌ 标记核心错误。每个错误写明：
   - 错误写法
   - 正确写法
   - 为什么错（中文解释，{level}学生能听懂）
3. **💡 更自然的说法**：至少提供一种更口语化/自然的日语表达
4. **📌 超纲拓展**（如适用）：简要讲解超纲语法点，注明"N2以上适用，了解即可"
5. **🎯 得分**：满分 10 分，按扣分规则计算
6. **💪 鼓励收尾**：一句鼓励的话

## 输出格式
请以 JSON 格式返回：
```json
{{
  "correct_parts": ["✅ 助词「が」使用正确，标记了动作主语", "✅ ..."],
  "error_parts": [
    {{
      "level": "⚠️",
      "error": "错误写法",
      "correction": "正确写法",
      "explanation": "为什么错了（中文解释）"
    }}
  ],
  "suggestions": "更自然的日语说法，附中文说明为什么更自然",
  "score": 7.5,
  "extra_notes": "超纲内容讲解（仅超纲题，否则为null）",
  "encouragement": "一句鼓励的话，比如：很棒！继续加油💪"
}}
```

请严格按照 JSON 格式返回。"""

    return prompt


def build_regenerate_question_prompt(grammar_point: str, level: str, original_question: dict, learned_items: list = None, question_type: str = "translation") -> str:
    """构建换题 prompt — 同语法点、同难度、完全不同的场景。M4 新增 question_type 参数。"""

    qt = original_question.get("question_type", question_type)

    # 构建可用语法清单（仅限已学内容）
    allowed_grammar = ""
    if learned_items and len(learned_items) > 0:
        items = [item.get("grammar_point", "") for item in learned_items if item.get("grammar_point")]
        if items:
            allowed_list = "、".join(items)
            allowed_grammar = f"""
## ⚠️ 语法范围限制
新题**只能**使用以下语法点（这些都是学生已经学过的）：
  {allowed_list}

除此之外的语法一律不要出现。如果这些已学语法中只有核心语法点「{grammar_point}」可用，那就只考这一个语法点，搭配最基础的です/ます/て形即可，**不要擅自引入学生没学过的语法**。
"""
    else:
        allowed_grammar = f"""
## ⚠️ 语法范围限制
学生目前没有已学语法记录。新题**只能考察**「{grammar_point}」这一个语法点，搭配该级别最基础的です/ます/て形即可。
**不要擅自引入任何学生没学过的语法。**
"""

    # 根据题型选择不同的输出格式（M4）
    if qt == "fill_blank":
        output_format = f"""{{
  "id": 99,
  "question_type": "fill_blank",
  "grammar_point": "{grammar_point}",
  "scene": "新的生活场景",
  "stem": "包含＿＿＿＿的日语句子",
  "options": ["选项A", "选项B", "选项C", "选项D"],
  "correct_option": 0,
  "blank_position": "空白的位置描述",
  "explanation": "为什么正确答案是对的",
  "hints": ["词汇1（よみ）- 意思"],
  "difficulty": 1,
  "is_extra": false,
  "extra_level": null
}}"""
        extra_req = "- 生成 4 个选项（都是正确自然的日语，差异在语法是否正确）\n- 空白处用 ＿＿＿＿ 表示\n- correct_option 为 0-based 索引"
        original_desc = f"- stem（含空白）：{original_question.get('stem', '')}\n- 正确答案索引：{original_question.get('correct_option', '')}"
    else:
        output_format = f"""{{
  "id": 99,
  "question_type": "translation",
  "grammar_point": "{grammar_point}",
  "scene": "新的生活场景（详细描述场合、人物关系等）",
  "chinese": "要表达的意思（口语化的中文）",
  "hints": ["词汇1（よみ）- 意思", "词汇2（よみ）- 意思"],
  "reference_answer": "参考答案",
  "difficulty": 1,
  "is_extra": false,
  "extra_level": null
}}"""
        extra_req = ""
        original_desc = f"- 场景：{original_question.get('scene', '')}\n- 要表达的意思：{original_question.get('chinese', '')}\n- 参考答案：{original_question.get('reference_answer', '')}"

    prompt = f"""你是日语教师。学生做错了关于「{grammar_point}」的题目，需要换一道**同语法点、同难度**的新题来巩固。

学生级别：{level}

## 原题（不要重复出一样的题）
{original_desc}
{allowed_grammar}

## 要求
- 必须考察同一个语法点：{grammar_point}
- 保持同难度（单语法点 + 基础表达即可，不要拔高）
- **换一个完全不同的生活场景**
- 给出足够全面的词汇提示（动词和有汉字的词都要给读音）
{extra_req}

## 输出格式（与正常题目格式一致）
```json
{output_format}
```

只返回 JSON。"""

    return prompt


def build_harder_question_prompt(grammar_point: str, level: str, original_question: dict, current_difficulty: int, learned_items: list = None, question_type: str = "translation") -> str:
    """构建加大难度 prompt — 只能在已学语法范围内组合。M4 新增 question_type 参数。"""

    next_diff = min(current_difficulty + 1, 3)
    qt = original_question.get("question_type", question_type)

    # 构建可用语法清单
    allowed_grammar = ""
    if learned_items and len(learned_items) > 0:
        items = [item.get("grammar_point", "") for item in learned_items if item.get("grammar_point")]
        # 过滤掉当前语法点本身
        other_items = [i for i in items if i != grammar_point]
        if other_items:
            allowed_list = "、".join(other_items[:15])  # 最多列15个，避免太长
            allowed_grammar = f"""
## ⚠️ 语法范围限制（非常重要！）
进阶题**只能**组合以下已学语法（这些都是学生已经学过的）：
  {allowed_list}

除核心语法点「{grammar_point}」外，从上面列表中选择 1~2 个来组合。
**严禁使用列表之外的任何语法！** 学生没学过的语法一律不要出现。
如果列表中的语法都不适合组合，就只用核心语法点搭配最基础的表达，加长场景和句子即可。
"""
        else:
            allowed_grammar = f"""
## ⚠️ 语法范围限制
学生目前只学过「{grammar_point}」这一个语法点。进阶题**只用这一个语法点**，通过加长场景、增加句子复杂度来提升难度，**不要引入任何学生没学过的语法**。
"""
    else:
        allowed_grammar = f"""
## ⚠️ 语法范围限制
学生目前没有已学语法记录。进阶题**只能考察「{grammar_point}」这一个语法点**，通过加长场景、增加句子细节来提升难度。
**严禁使用任何学生没学过的语法！**
"""

    diff_desc = {
        2: f"""中级难度：
- 核心语法点还是「{grammar_point}」
- 如果有已学语法可以组合 → 选 1 个最合适的搭配
- 如果没有合适的 → 把场景写得更丰富、句子更长，但只用一个语法点
- 「要表达的句子」为 2~3 句构成的段落，日常对话风格""",
        3: f"""高级难度：
- 核心语法点还是「{grammar_point}」
- 如果有已学语法可以组合 → 选 2 个最合适的搭配
- 如果没有合适的 → 把场景写成一个小故事，3~4 句构成
- 「要表达的句子」为 3~4 句构成的小段落，像在叙述一件日常小事""",
    }

    desc = diff_desc.get(next_diff, diff_desc[2])

    # 根据题型选择不同的输出格式（M4）
    if qt == "fill_blank":
        harder_desc = desc.replace("要表达的句子", "填空句")
        output_format = f"""{{
  "id": 99,
  "question_type": "fill_blank",
  "grammar_point": "{grammar_point}",
  "scene": "新的生活场景",
  "stem": "包含＿＿＿＿的日语句子（难度 Lv{next_diff}）",
  "options": ["选项A", "选项B", "选项C", "选项D"],
  "correct_option": 0,
  "blank_position": "空白的位置描述",
  "explanation": "为什么正确答案是对的",
  "hints": ["词汇1（よみ）- 意思", "词汇2（よみ）- 意思"],
  "difficulty": {next_diff},
  "is_extra": false,
  "extra_level": null
}}"""
        extra_req = "- 干扰项基于常见学习者错误设计\n- 空白处用 ＿＿＿＿ 表示\n- correct_option 为 0-based 索引\n- 所有 4 个选项都必须是正确自然的日语"
        original_desc = f"- stem（含空白）：{original_question.get('stem', '')}\n- 正确答案索引：{original_question.get('correct_option', '')}"
    else:
        harder_desc = desc
        output_format = f"""{{
  "id": 99,
  "question_type": "translation",
  "grammar_point": "{grammar_point}",
  "scene": "新的生活场景",
  "chinese": "要表达的意思（2~4句，难度对应 Lv{next_diff}）",
  "hints": ["词汇1（よみ）- 意思", "词汇2（よみ）- 意思"],
  "reference_answer": "参考答案",
  "difficulty": {next_diff},
  "is_extra": false,
  "extra_level": null
}}"""
        extra_req = ""
        original_desc = f"- 场景：{original_question.get('scene', '')}\n- 要表达的意思：{original_question.get('chinese', '')}"

    prompt = f"""你是日语教师。学生上一题答得很好，现在要加大难度！

学生级别：{level}
当前语法点：{grammar_point}
当前难度：Lv{current_difficulty} → 升级到 Lv{next_diff}

## 原题（参考，不要重复）
{original_desc}
{allowed_grammar}

## 升级要求
{harder_desc}

- 核心语法点仍然是「{grammar_point}」
- 场景换一个新的
- 所有难度都在日常对话/叙述范围内，不要出现书面论文用语
- 词汇提示给全（动词和有汉字的词都要给读音）
- 标记 difficulty={next_diff}
{extra_req}

## 输出格式
```json
{output_format}
```

只返回 JSON。"""

    return prompt


def build_essay_grade_prompt(essay_question: dict, user_answer: str, level: str) -> str:
    """构建作文批改 prompt — 只检查语法正确性和自然流畅度，不强求覆盖全部语法点。"""

    scene = essay_question.get("scene", "")
    chinese = essay_question.get("chinese", "")
    reference = essay_question.get("reference_answer", "")
    fmt = essay_question.get("format", "")

    prompt = f"""你是一位日语教师，正在批改{level}级别学生的综合短文写作。

## 题目
- 场景背景：{scene}
- 表达方式：{fmt}
- 要写的内容：{chinese}
- 参考答案（仅为其中一种写法）：{reference}

## 学生答案
{user_answer}

## 作文批改原则

**这是自由写作练习，不是逐字翻译，也不是语法点考试。**

- 学生不需要用到本轮全部的语法点——用上几个算几个，不用也不扣分
- 参考答案只是**示例**，学生可以自由发挥
- 评判标准只有两条：
  1. **语法是否正确**：助词、时态、接续有无明显错误
  2. **表达是否自然流畅**：读起来像不像日语句子，段落衔接是否顺畅
- **多鼓励、少扣分**——能写出一段连贯的日语本身就是很好的表现

## 评分标准（满分 10 分）
| 维度 | 分值 | 说明 |
|------|------|------|
| 语法准确性 | 5 分 | 助词、时态、接续是否正确（小错少扣，大错多扣） |
| 整体流畅度 | 3 分 | 读起来是否自然，段落衔接是否顺畅 |
| 表达丰富度 | 2 分 | 词汇和句式是否多样，是否恰到好处地使用了一些接续表现 |

**注意：不考察语法点覆盖率。语法点用多用少、用哪个不用哪个，不影响评分。**

## 输出格式
```json
{{
  "correct_parts": ["✅ 正确使用了〜てから表达先后顺序"],
  "error_parts": [
    {{
      "level": "⚠️",
      "error": "错误写法",
      "correction": "正确写法",
      "explanation": "解释"
    }}
  ],
  "grammar_check": [
    {{"grammar": "〜てから", "used": true, "correct": true, "note": "使用正确"}}
  ],
  "suggestions": "整体评价 + 更自然的改写建议",
  "score": 7.5,
  "encouragement": "鼓励的话"
}}
```

grammar_check 中**只列出学生实际使用了的语法点**，给出评价。未使用的语法点不需要列出，更不要因此扣分。

只返回 JSON。"""

    return prompt
