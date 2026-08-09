"""
出题 Prompt 构建模块

出题格式：场景描述 + 要表达的句子（而非逐字翻译）。
难度递进：初级复句 → 中级多从句 → 高级综合叙事，均在日常生活语言范畴内。

M4 新增：question_type 参数（translation / fill_blank / mixed）+ focus_tags 参数。
"""


def build_generate_questions_prompt(notes: str, level: str, learned_content: list = None, vocab_text: str = "", vocab_bank: list = None, textbook_vocab: list = None, question_type: str = "translation", focus_tags: list = None) -> str:
    """构建出题 prompt — 场景化表达，渐进式难度。支持翻译/填空/混合三种题型。"""

    # JLPT 级别范围说明
    level_scope = {
        "N5": """N5 入门（约 800 词 / 最基础句型）
✅ 可用：〜です/ます、〜たい、〜て形、〜ない形、〜た形、〜辞書形、〜ことができる、〜前に/〜後で、〜ましょう/〜ませんか
❌ 禁止：N4+ 语法（〜てから、〜ので、〜ながら、〜そうだ、授受动词、可能形、受身形、〜つもり、〜ところ、〜ば、〜なら）
📏 初级：1~2 个短句构成的复句，用最简单的接续（〜て、〜から、〜が）""",

        "N4": """N4 初级（约 1500 词 / 日常基础表达）
✅ 可用：N5 全部 + 〜てから、〜ので、〜ながら、〜そうだ（样态/传闻）、授受动词（あげる/くれる/もらう）、可能形、受身形、〜つもり、〜ところ、〜ば/〜なら（条件）、〜ようだ、使役形基础
❌ 禁止：N3+ 语法（〜わけだ、〜はずだ、〜ようにする/〜ことにする、尊敬語/謙譲語、〜にとって、〜として、〜に関して、〜一方で、〜せいで/〜おかげで）
📏 初级：2 个句子组成的复句，融入自然的接续词（しかし、それで、だから）""",

        "N3": """N3 中级（约 3000 词 / 社会生活场景）
✅ 可用：N4 全部 + 〜わけだ、〜はずだ、〜ようにする/〜ことにする、尊敬語/謙譲語基础、〜にとって、〜として、〜に関して、〜一方で、〜せいで/〜おかげで、〜たびに、〜に違いない
❌ 禁止：N2+ 语法（〜ものだ、〜わけではない、〜ざるを得ない、〜にかかわらず、〜に際して、〜に先立ち、〜まい、书面语/论文用语）
📏 中级：2~3 个句子，表达较复杂的意思，含推测/传闻/转折等""",

        "N2": """N2 中高级（约 6000 词 / 抽象话题可讨论）
✅ 可用：N3 全部 + 〜ものだ、〜わけではない、〜ざるを得ない、〜にかかわらず、〜に際して、〜を問わず、〜に限って、书面语表达、复合从句
❌ 禁止：N1 古典残留表达（〜べからず、〜まじき、〜や否や）、极度正式公文用语、文言语法
📏 高级：3~4 个句子的小段落，综合运用多种语法和接续表现""",

        "N1": """N1 高级（约 10000+ 词 / 几乎无限制）
✅ 可用：全部日语语法和词汇，包括古典残留表达、正式书面语、学术用语
❌ 无需限制
📏 高级：多句构成的完整段落""",
    }

    scope = level_scope.get(level, level_scope["N4"])

    # 已学语法内容
    learned_section = ""
    if learned_content and len(learned_content) > 0:
        items_desc = []
        for item in learned_content:
            gp = item.get("grammar_point", "")
            mastery = item.get("mastery", 0.5)
            emoji = "✅" if mastery >= 0.8 else ("⚠️" if mastery >= 0.5 else "❌")
            items_desc.append(f"  {emoji} {gp}（掌握度: {mastery:.0%}）")
        learned_section = f"""
## 学生已学语法点（可融入题目做螺旋复习，不算超纲）
{chr(10).join(items_desc)}

掌握度低的已学语法点应优先融入题目中帮助巩固。
"""

    # 今日单词
    vocab_section = ""
    if vocab_text:
        vocab_section = f"""
## 🆕 今日学习单词（请尽可能用在题目中！）
```
{vocab_text}
```
使用要求：
- 每道题至少融入 1~2 个今日单词到场景或要表达的句子中
- 自然融入，不要生硬堆砌
- 今日单词在词汇提示中**不给出**（让学生自己回忆）
"""

    # 教材单词
    textbook_section = ""
    if textbook_vocab and len(textbook_vocab) > 0:
        words_desc = []
        for v in textbook_vocab[:200]:  # 最多 200 个避免 prompt 过长
            w = v.get("word", "")
            r = v.get("reading", "")
            m = v.get("meaning", "")
            words_desc.append(f"  - {w}（{r}）{m}")
        word_list = "\n".join(words_desc)
        textbook_section = f"""
## 📖 教材单词范围（出题必须在此范围内！）
以下为当前课程的教材单词，出题时**只能使用列表中出现的单词**，不要引入列表外的新词：
{word_list}
"""
        if len(textbook_vocab) > 200:
            textbook_section += f"\n（仅显示前 200 个，共 {len(textbook_vocab)} 个词）"

    # 历史单词库
    vocab_bank_section = ""
    if vocab_bank and len(vocab_bank) > 0:
        recent = vocab_bank[-20:]
        words_desc = []
        for v in recent:
            w = v.get("word", "")
            r = v.get("reading", "")
            m = v.get("meaning", "")
            rc = v.get("review_count", 0)
            words_desc.append(f"  - {w}（{r}）{m} [复习{rc}次]")
        vocab_bank_section = f"""
## 📚 学生历史词库（最近 20 词，可辅助出题）
{chr(10).join(words_desc)}
"""

    # 专注知识点 —— 由答疑联动 / 教材语法点多选而来（M4 + M5.x）
    focus_section = ""
    if focus_tags and len(focus_tags) > 0:
        tag_list = "\n".join([f"  - {t}" for t in focus_tags])
        focus_section = f"""
## 🎯 本次练习专注知识点

以下知识点是本次练习的核心目标（来自答疑联动或教材语法点多选），请**优先围绕这些知识点出题**：
{tag_list}

所有题目必须紧扣上述知识点。笔记中其他语法点可作为辅助。
"""

    # 题型分叉 —— 格式说明（M4 新增）
    if question_type == "fill_blank":
        format_section = """## 🔤 题型：挖空选择题

每道题是四选一的选择题格式，由以下字段组成：

### 字段说明
- **scene**：场景描述（同翻译题型，生动具体的生活场景）
- **stem**：包含空白的日语句子，空白处用 ＿＿＿＿ 表示（4 个全角下划线）
- **options**：4 个日语选项（**必须是完整、自然的日语表达**，不是单词拼接），只有 1 个是正确答案
- **correct_option**：正确答案在 options 中的索引（0-based，即 0/1/2/3）
- **blank_position**：中文描述空白的位置（如"在助词を之后"），帮助学生定位
- **explanation**：一句话解释为什么正确答案是对的（中文）
- **grammar_point**：考察的语法点
- **hints**：词汇提示（规则与翻译题型相同）
- **difficulty**：1=基础，2=进阶，3=挑战
- **is_extra / extra_level**：超纲标记

### 干扰项要求
- 所有 4 个选项都必须是**正确、自然的日语**（都读得通），差异在于**语法是否符合语境**
- 干扰项应为常见学习者错误（助词混用、时态错、形变错等），不要编造不存在的日语
- 避免长度差异过大的选项泄题"""
    elif question_type == "mixed":
        format_section = """## 🎲 题型：混合模式

每道题**各自标注 question_type**，约一半为 "translation"（情景翻译），一半为 "fill_blank"（挖空选择）。两种题型交错排列。

### 翻译题格式（question_type: "translation"）
包含 scene / chinese / hints / reference_answer，与标准翻译题型一致。

### 选择题格式（question_type: "fill_blank"）
包含 scene / stem / options[4] / correct_option / blank_position / explanation，与标准选择题型一致。

选择题的 options 必须全部是正确自然的日语，干扰项基于常见学习者错误设计。"""
    else:
        format_section = """## 📝 题型：情景翻译

每道题由两部分组成：

### ① 场景描述（scene）
详细描写一个**具体的生活场景**，让读者清楚"我在哪、在对谁说话、发生了什么"。
场景要生动、有画面感，让学习者产生"我好像真的在那里"的感觉。

### ② 要表达的句子（chinese）
在这个场景下，**你想说什么**。这是用中文写的"你想表达的意思"，不是让学习者逐字翻译。
学习者需要根据场景和你想表达的意思，用日语说出来。

**示例：**
> 场景：你是一位日本公司的前辈，正在指导一位刚入职的后辈使用公司内部的考勤系统。后辈看着电脑屏幕，不知道哪个按钮是「提交申请」。你指着屏幕上的按钮，想告诉他：
>
> 要表达的句子：「这个按钮是"提交"的意思，请点击它。」"""

    prompt = f"""你是一位精通日语教学的私人教练。你的学生是{level}级别的日语学习者。

## 学生级别
{scope}

## 学生今日语法笔记
```
{notes if notes.strip() else "（未提供笔记——请严格依据下方「本次练习专注知识点」列出的语法点出题）"}
```
{focus_section}{learned_section}{textbook_section}{vocab_section}{vocab_bank_section}
---

{format_section}

---

## 📝 出题规则

### 1. 不是翻译题！
你给出的 chinese 是**要表达的意思**，不是让学习者做机械翻译。学习者需要在理解场景的基础上，用日语自然地表达出来。因此：
- chinese 用口语化的中文写，像"你想说的话"而不是"考试题"
- 参考答案只是其中一种正确的日语说法，允许学习者用不同的词汇/句式表达同样的意思

### 2. 难度递进（全部在日常对话范畴内）
| 级别 | 题目难度 | 参考示例 |
|------|---------|---------|
| 初级 | 1~2 句构成的复句。可以是本课语法+知识库旧语法组合，也可以搭配一个学生应该会的基础表达 | 「课长，我想向您传达小李今天休息这件事。」 |
| 中级 | 2~3 句，表达较复杂的意思，含推测/传闻/转折/因果关系 | 「嗯，我也这么觉得。那个人好像从刚才开始就一直在看手表，可能是在等女朋友吧。」 |
| 高级 | 3~4 句的小段落，综合运用多种语法和接续表现，像一个微型小故事 | 「是啊。我最近在备考，所以每天一边听英语一边学习。说起来，上次在图书馆遇到了田中，他借给了我一本很好的参考书。那本参考书内容很充实，而且解释也很容易懂。」 |

**所有难度都保持在日常会话的范围内**——不出现书面语论文、不出现极端正式的公务用语。

### 3. 逐点出题
- 从笔记中提取每个独立语法点，每个语法点先出 1 道基础题
- 从最简单、最常用的语法点开始排列
- 如果提供了今日单词，自然融入场景和要表达的句子中

### 4. 超纲标记
如果某个语法点明显超出{level}范围，标记 is_extra=true，注明适用级别。

---

## 💡 词汇提示规则（非常重要！）

**提示要给全！** 学生可能不认识的词汇全部给出提示，尤其是：
- **所有动词**：给出辞书形 + 读音（ひらがな）+ 中文意思
- **有汉字的词**：必须给出ひらがな注音
- 提示格式：`漢字（かんじ）- 中文意思`

不要在提示中直接暴露考察的语法点（如不要提示"〜てから"本身），但可以提示相关的实词。

---

## 题目难度分层
- 基础题（第1轮）：考察**单个**语法点，可搭配知识库中的旧语法或基础表达构成复句。
- 进阶题（第2轮）：同时结合**2个**语法点，含转折/因果等逻辑关系。
- 挑战题（第3轮）：综合考察 3~4 个语法点，3~4 句构成的小段落。

**本次只出第一轮基础题**（每个语法点 1 题）。进阶和挑战题在用户答得好时由系统另外请求。

---

## 总题数限制
- 最少 4 题，最多 12 题
- 如果笔记中语法点超过 12 个，优先选择最核心的 12 个

---

## 输出格式
严格按以下 JSON 格式返回，不要包含其他文字：
```json
{{
  "total": 8,
  "question_type": "{question_type}",
  "grammar_points_found": ["语法点1", "语法点2", ...],
  "vocab_used": ["用到的今日单词1", ...],
  "questions": ["""

    # 根据题型拼接不同的 question 示例
    if question_type == "fill_blank":
        prompt += """
    {{
      "id": 1,
      "question_type": "fill_blank",
      "grammar_point": "〜てから",
      "scene": "教室で友達と会話している",
      "stem": "朝ごはんを＿＿＿＿、学校に行きます。",
      "options": ["食べる", "食べてから", "食べた", "食べます"],
      "correct_option": 1,
      "blank_position": "在「を」之后、动词的位置",
      "explanation": "「〜てから」表示做完前项后再做后项",
      "hints": ["朝ごはん（あさごはん）- 早饭"],
      "difficulty": 1,
      "is_extra": false,
      "extra_level": null
    }}
  ]
}}
```"""
    elif question_type == "mixed":
        prompt += """
    {{
      "id": 1,
      "question_type": "translation",
      "grammar_point": "〜てから",
      "scene": "你是公司的新人...",
      "chinese": "我处理完这封邮件之后去拜访客户。",
      "hints": ["処理（しょり）- 处理", "取引先（とりひきさき）- 客户"],
      "reference_answer": "このメールを処理してから取引先を訪ねます。",
      "difficulty": 1,
      "is_extra": false,
      "extra_level": null
    }},
    {{
      "id": 2,
      "question_type": "fill_blank",
      "grammar_point": "〜ないで",
      "scene": "朋友问你为什么没带伞",
      "stem": "天気予報を見＿＿＿＿、出かけました。",
      "options": ["ない", "なくて", "ないで", "ません"],
      "correct_option": 2,
      "blank_position": "在「見」之后",
      "explanation": "〜ないで表示不做前项就做后项",
      "hints": ["天気予報（てんきよほう）- 天气预报"],
      "difficulty": 1,
      "is_extra": false,
      "extra_level": null
    }}
  ]
}}
```"""
    else:
        prompt += """
    {{
      "id": 1,
      "question_type": "translation",
      "grammar_point": "〜てから",
      "scene": "你是公司的新人，刚和同事吃完午饭回到办公室。前辈问你等下有什么安排，你想告诉他你打算处理完邮件后去拜访客户。",
      "chinese": "我处理完这封邮件之后去拜访客户。",
      "hints": [
        "処理（しょり）- 处理",
        "取引先（とりひきさき）- 客户",
        "訪ねる（たずねる）- 拜访"
      ],
      "reference_answer": "このメールを処理してから取引先を訪ねます。",
      "difficulty": 1,
      "is_extra": false,
      "extra_level": null
    }}
  ]
}}
```"""

    prompt += """

difficulty 取值：1=基础题（单语法点），2=进阶题（2个语法点组合），3=挑战题（3~4个语法点综合）。
vocab_used：列出本次出题中用到的今日单词（如果有的话）。
question_type：顶层为本次练习的题型标识（"{question_type}"），每题内部也标注 question_type。
"""

    return prompt


def build_essay_question_prompt(grammar_points: list, level: str, notes: str, vocab_bank: list = None) -> str:
    """构建终极挑战作文题 prompt — 叙事转述型作文。"""

    points_text = "\n".join([f"  - {gp}" for gp in grammar_points])

    scope = {
        "N5": "N5 入门。句型限于 〜です/ます、〜たい、〜て形、〜ない形、〜た形，简单日常词汇。",
        "N4": "N4 初级。可用 〜てから、〜ので、〜ながら、〜そうだ、授受动词、可能形、受身形、〜つもり 等。",
        "N3": "N3 中级。可用 〜わけだ、〜はずだ、〜ようにする、尊敬語/謙譲語 等。",
        "N2": "N2 中高级。可用 〜ものだ、〜わけではない、书面语表达、复合从句。",
        "N1": "N1 高级。全部语法可用。",
    }.get(level, "N4 初级")

    # 单词库
    vocab_bank_section = ""
    if vocab_bank and len(vocab_bank) > 0:
        recent = vocab_bank[-30:]
        words_desc = []
        for v in recent:
            w = v.get("word", "")
            r = v.get("reading", "")
            m = v.get("meaning", "")
            words_desc.append(f"  - {w}（{r}）{m}")
        vocab_bank_section = f"""
## 📚 学生词库
{chr(10).join(words_desc)}
"""

    prompt = f"""你是一位日语教师，学生刚完成了一轮{level}级别的语法练习。现在需要一道**终极挑战作文题**。

学生级别：{level}
级别范围：{scope}

## 本轮涉及的语法点（仅供参考，不强求全部用到）
{points_text}

## 原始笔记参考
{notes[:500]}
{vocab_bank_section}

---

## 📝 作文题格式（三部分组成）

作文题由三个独立字段组成：

### ① 场景描述（scene）
发生了什么。一段生动的生活叙事，像在讲一个小故事，有人物、有对话、有细节。
**注意：这是背景信息，不是让学生翻译的内容。**

### ② 表达方式（format）
一句话说明"以什么形式来表达"。例如：
- 「📝 以日记形式记录今天的事」
- 「💬 向朋友转述昨天发生的事」
- 「📱 给家人发消息讲述」

**注意：format 必须独立写在 format 字段中，不要混入 chinese 字段！**

### ③ 要写的内容（chinese）
**纯内容**，学生需要用日语写出来的东西。不要包含任何"你以日记形式写道："这类框架性文字。
这部分就是日记正文、转述内容、消息文字本身——干净、纯粹。

---

## 🎯 出题要求
1. 场景要生动、日常，有画面感
2. chinese 是纯内容，**绝对不要**在里面写"你回家后在日记里写道："或"你跟朋友说："这类框架句
3. 表达方式（format）独立写一句即可
4. 给出 5~8 个关键词汇提示（日语+读音+中文），提示要给全
5. **不强求用到所有语法点**——学生能自然用上几个算几个

---

## 风格参考
> **场景描述：**
> 你周末去朋友小野家玩。小野正在一边听广播（ラジオ）一边做晚饭。你到了之后，小野说："你来得正好，我正要做咖喱（カレー），但发现家里没有胡萝卜（にんじん）了。"
> 你听后，主动说："那我去附近的便利店买吧。"于是你出门买了胡萝卜回来。小野做好咖喱后，盛了一碗给你。你吃了一口，觉得非常好吃，而且发现小野还在咖喱里加了苹果（りんご），味道很特别。
>
> **表达方式：**
> 📝 以日记形式记录今天的事
>
> **要写的内容：**
> 今天去了小野家。到的时候他正一边听广播一边做晚饭。他说家里没有胡萝卜了，我就去附近的便利店帮他买了。小野做的咖喱非常好吃！里面还加了苹果，味道很特别。今天很开心。

---

## 输出格式
```json
{{
  "scene": "场景描述（发生了什么事，有人物、有对话、有细节）",
  "format": "表达方式（一句话，如：📝 以日记形式记录）",
  "chinese": "要写的内容（纯内容，不要框架性文字！）",
  "hints": [
    "放送（ほうそう）- 广播",
    "人参（にんじん）- 胡萝卜",
    "近所（きんじょ）- 附近",
    "林檎（りんご）- 苹果"
  ],
  "reference_answer": "日语参考译文",
  "grammar_points_covered": ["可能用到的语法点1", "可能用到的语法点2"]
}}
```

**关键：chinese 字段只写纯内容！不要把表达方式混进去！**

只返回 JSON。"""

    return prompt
