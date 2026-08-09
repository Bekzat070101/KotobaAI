/* ============================================================
   KOTOBA·AI — 前端交互逻辑
   状态管理 / API 交互 / 屏幕切换 / 进度保存
   ============================================================ */

// --- 全局状态 ---
const AppState = {
    config: { api_key: "", level: "N3", model: "deepseek-chat", learning_goal: "" },
    questions: [],          // 全部题目
    currentIndex: 0,        // 当前题目索引
    records: [],            // 答题记录
    notes: "",              // 原始笔记
    vocabulary: "",         // 今日单词（原始文本）
    vocabUsed: [],          // AI 出题中用到的今日单词
    totalAnswered: 0,       // 已答题数（含加练/换题）
    baseTotal: 0,           // 原始题目总数（进度条分母）
    historyDate: null,      // 查看历史详情时的日期
    questionType: "translation",  // M4: 题型 "translation" | "fill_blank" | "mixed"
    fillblankSelected: null,      // M4: 填空选择题选中的选项索引
    selectedGrammarPoints: [],     // M5.x: 教材语法点多选 [{point, explanation}]
};

// --- 工具函数 ---
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function show(el) { el.style.display = ""; }
function hide(el) { el.style.display = "none"; }
function maskKey(key) {
    if (!key) return "未设置";
    return key.slice(0, 5) + "••••" + key.slice(-4);
}
function escapeHtml(s) {
    return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// --- 界面缩放（Ctrl + / - / 0，和浏览器一致）---
function initZoom() {
    const root = document.documentElement;
    let scale = parseFloat(localStorage.getItem("kotoba-ui-scale") || "1");
    // 限制范围
    scale = Math.max(0.5, Math.min(2.5, scale));
    root.style.setProperty("--ui-scale", scale);
    localStorage.setItem("kotoba-ui-scale", scale);

    document.addEventListener("keydown", (e) => {
        if (!e.ctrlKey && !e.metaKey) return;
        // 输入框内不拦截
        if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;

        let target = null;
        if (e.key === "=" || e.key === "+" || e.code === "Equal" || e.code === "NumpadAdd") {
            // Ctrl+= 放大（按 shift 出的 + 也识别）
            target = Math.min(2.5, scale + 0.1);
        } else if (e.key === "-" || e.code === "Minus" || e.code === "NumpadSubtract") {
            // Ctrl+- 缩小
            target = Math.max(0.5, scale - 0.1);
        } else if (e.key === "0" || e.code === "Digit0" || e.code === "Numpad0") {
            // Ctrl+0 重置
            target = 1;
        }

        if (target !== null) {
            e.preventDefault();
            scale = Math.round(target * 10) / 10; // 一位小数精度
            root.style.setProperty("--ui-scale", scale);
            localStorage.setItem("kotoba-ui-scale", scale);
        }
    });
}
initZoom();

// --- API 封装 ---
async function api(url, options = {}) {
    try {
        const res = await fetch(url, {
            headers: { "Content-Type": "application/json" },
            ...options,
        });
        const data = await res.json();
        if (!res.ok) {
            // 优先显示服务器返回的错误信息
            throw new Error(data.error || `请求失败 (HTTP ${res.status})`);
        }
        return data;
    } catch (err) {
        // 如果服务器返回了明确的错误，直接抛出
        if (err.message && !err.message.includes("Failed to fetch")) {
            throw err;
        }
        // 否则是网络不通（服务器没启动或已崩溃）
        throw new Error(
            "无法连接到本地服务 (http://127.0.0.1:5000)\n\n" +
            "请检查：\n" +
            "1. 命令行窗口是否还在运行（没被关闭）\n" +
            "2. 命令行窗口中是否有红色的报错信息\n" +
            "3. 如果服务已崩溃，请重新双击 启动.bat"
        );
    }
}

// --- 屏幕管理 ---
function showScreen(name) {
    $$(".screen").forEach(s => hide(s));
    const screen = $(`#screen-${name}`);
    if (screen) show(screen);
}

function showLoading(text = "加载中...") {
    $("#loading-text").textContent = text;
    show($("#screen-loading"));
}

function hideLoading() {
    hide($("#screen-loading"));
}

// --- 简单 Markdown → HTML ---
function renderMarkdown(md) {
    if (!md) return "";
    let html = md
        // 标题
        .replace(/^### (.+)$/gm, "<h3>$1</h3>")
        .replace(/^## (.+)$/gm, "<h2>$1</h2>")
        .replace(/^# (.+)$/gm, "<h1>$1</h1>")
        // 粗体
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        // 代码块
        .replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>")
        // 行内代码
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        // 水平线
        .replace(/^---$/gm, "<hr>")
        // 无序列表
        .replace(/^- (.+)$/gm, "<li>$1</li>")
        // 有序列表
        .replace(/^\d+\. (.+)$/gm, "<li>$1</li>")
        // 引用
        .replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>")
        // 段落（连续非空行）
        .replace(/\n\n/g, "</p><p>")
        // 换行
        .replace(/\n/g, "<br>");

    html = "<p>" + html + "</p>";
    // 包裹连续的 li
    html = html.replace(/(<li>.*?<\/li>)+/g, "<ul>$&</ul>");
    // 清理空标签
    html = html.replace(/<p><\/p>/g, "");
    html = html.replace(/<p>(<h[123]>)<\/p>/g, "$1");
    html = html.replace(/(<\/h[123]>)<\/p>/g, "$1");
    html = html.replace(/<p>(<ul>)<\/p>/g, "$1");
    html = html.replace(/(<\/ul>)<\/p>/g, "$1");

    return html;
}

// --- 字符计数 ---
function updateCharCount() {
    const text = $("#notes-input").value;
    $("#char-count").textContent = `${text.length} 字`;
}

function updateVocabCharCount() {
    const text = $("#vocab-input").value;
    $("#vocab-char-count").textContent = `已输入 ${text.split('\n').filter(l => l.trim()).length} 个单词`;
}

// --- 配置管理 ---
async function loadConfig() {
    try {
        const data = await api("/api/config");
        AppState.config = data;
        return data;
    } catch {
        return null;
    }
}

async function saveConfig(config) {
    await api("/api/config", {
        method: "POST",
        body: JSON.stringify(config),
    });
    AppState.config = { ...AppState.config, ...config };
}

// ============================================================
// 屏幕 -1：使用指南
// ============================================================
async function initGuideScreen() {
    // 如果已经设置过 API Key，跳过指南直接进入
    const data = await loadConfig();
    if (data && data.has_api_key) {
        initMainScreen();
        return;
    }

    showScreen("guide");
    setDockActive("guide");

    // 开始使用 → 如果已有 Key 直接进练习，否则进入设置页
    $("#btn-guide-start").onclick = async () => {
        const data = await loadConfig();
        if (data && data.has_api_key) {
            initMainScreen();
        } else {
            initSetupScreen();
        }
    };
}

// ============================================================
// 屏幕 1：API Key 设置
// ============================================================
async function initSetupScreen() {
    const data = await loadConfig();
    if (data && data.has_api_key) {
        // 已有 API Key，跳过设置页
        initMainScreen();
        return;
    }

    showScreen("setup");
    setDockActive("settings");
    $("#api-key-input").value = "";
    $("#setup-error").style.display = "none";

    $("#btn-save-key").onclick = async () => {
        const key = $("#api-key-input").value.trim();
        if (!key) {
            showError("setup-error", "请输入 API Key");
            return;
        }
        if (!key.startsWith("sk-")) {
            showError("setup-error", "API Key 格式不正确，应以 sk- 开头");
            return;
        }
        try {
            await saveConfig({ api_key: key });
            initMainScreen();
        } catch (err) {
            showError("setup-error", err.message);
        }
    };

    $("#btn-skip-setup").onclick = () => {
        initMainScreen();
    };

    // 回车提交
    $("#api-key-input").onkeydown = (e) => {
        if (e.key === "Enter") $("#btn-save-key").click();
    };
}

function showError(id, msg) {
    const el = $(`#${id}`);
    el.textContent = msg;
    show(el);
}

// ============================================================
// 屏幕 2：主页（级别选择 + 笔记输入）
// ============================================================
async function initMainScreen() {
    hideLoading();

    // 检查是否有未完成进度
    try {
        const progress = await api("/api/progress");
        if (progress.has_progress && progress.data) {
            showResumeModal(progress.data);
            return;
        }
    } catch {
        // 忽略错误，继续正常流程
    }

    showMainScreen();
}

function showMainScreen() {
    showScreen("main");
    setDockActive("main");

    // 加载教材列表
    loadTextbookOptions();

    // 检查今日复习
    loadReviewStatus();

    // 加载迷你打卡卡片
    loadCheckinMini();

    // 设置默认级别
    const level = AppState.config.level || "N3";
    $$(".level-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.level === level);
    });

    // 恢复笔记内容
    if (AppState.notes) {
        $("#notes-input").value = AppState.notes;
        updateCharCount();
    }

    // 恢复单词内容
    if (AppState.vocabulary) {
        $("#vocab-input").value = AppState.vocabulary;
        updateVocabCharCount();
    }

    // 级别选择
    $$(".level-btn").forEach(btn => {
        btn.onclick = () => {
            $$(".level-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            AppState.config.level = btn.dataset.level;
        };
    });

    // 题型选择（M4）
    const qtype = AppState.questionType || "translation";
    $$(".qtype-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.qtype === qtype);
        btn.onclick = () => {
            $$(".qtype-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            AppState.questionType = btn.dataset.qtype;
        };
    });

    // 字数统计
    $("#notes-input").oninput = updateCharCount;
    $("#vocab-input").oninput = updateVocabCharCount;

    // 开始训练
    $("#btn-start").onclick = startTraining;
}

async function startTraining() {
    const notes = $("#notes-input").value.trim();
    const focusTags = (AppState.selectedGrammarPoints || []).map(g => g.point);
    if (!notes && focusTags.length === 0) {
        showError("main-error", "请先粘贴语法笔记，或选择语法点范围");
        return;
    }

    const level = AppState.config.level;
    const vocabEnabled = $("#vocab-enabled").checked;
    const vocabText = vocabEnabled ? $("#vocab-input").value.trim() : "";

    showLoading("正在生成题目...");
    hide($("#main-error"));

    try {
        const result = await api("/api/generate_questions", {
            method: "POST",
            body: JSON.stringify({ notes, level, vocabulary: vocabText, textbook_vocab: currentBookVocab, question_type: AppState.questionType, focus_tags: focusTags }),
        });

        if (!result.success || !result.data) {
            throw new Error("出题失败，请重试");
        }

        AppState.notes = notes;
        AppState.vocabulary = vocabText;
        AppState.questions = result.data.questions || [];
        AppState.vocabUsed = result.data.vocab_used || [];
        AppState.currentIndex = 0;
        AppState.records = [];
        AppState.totalAnswered = 0;
        AppState.baseTotal = AppState.questions.length;

        if (AppState.questions.length === 0) {
            throw new Error("未能从笔记中提取到语法点，请检查笔记内容");
        }

        // 保存初始进度
        await saveProgress();

        hideLoading();
        initQuizScreen();
    } catch (err) {
        hideLoading();
        showError("main-error", err.message);
    }
}

// ============================================================
// 屏幕 3：答题界面
// ============================================================
function initQuizScreen() {
    showScreen("quiz");
    $("#feedback-area").style.display = "none";
    renderCurrentQuestion();
}

function getCurrentQuestion() {
    // 如果 currentIndex 超出原始题目范围，说明当前是加练/换题的新题
    if (AppState.currentIndex < AppState.questions.length) {
        return AppState.questions[AppState.currentIndex];
    }
    // 从 records 中获取最后一道题的 question（加练/换题场景）
    if (AppState.records.length > 0) {
        return AppState.records[AppState.records.length - 1].question;
    }
    return null;
}

function renderCurrentQuestion() {
    const q = getCurrentQuestion();
    if (!q) return;

    // 步骤圆点
    const steps = $("#quiz-steps");
    if (steps && AppState.baseTotal > 0) {
        let dots = "";
        for (let i = 0; i < AppState.baseTotal; i++) {
            let cls = "quiz-step-dot";
            if (i < AppState.currentIndex) cls += " done";
            if (i === AppState.currentIndex) cls += " current";
            dots += `<span class="${cls}"></span>`;
        }
        steps.innerHTML = dots;
    }

    // 累计得分
    const totalScore = AppState.records.reduce((sum, r) => {
        return sum + (r.feedback?.score || 0);
    }, 0);
    const avgScore = AppState.records.length > 0
        ? (totalScore / AppState.records.length).toFixed(1)
        : "--";
    $("#progress-score").textContent = AppState.records.length > 0
        ? `均分 ${avgScore} | 已答 ${AppState.records.length}`
        : "";

    // 超纲标签
    if (q.is_extra) {
        show($("#badge-extra"));
        $("#badge-extra").textContent = `📌 拓展（${q.extra_level || "超纲"}）`;
    } else {
        hide($("#badge-extra"));
    }

    // 难度标签
    if (q.difficulty >= 2) {
        show($("#badge-difficulty"));
        const flames = "🔥".repeat(Math.min(q.difficulty, 3));
        $("#badge-difficulty").textContent = `${flames} Lv${q.difficulty}`;
    } else {
        hide($("#badge-difficulty"));
    }

    // 语法点
    $("#grammar-tag").textContent = q.grammar_point || "";

    // --- 题型分支（M4）---
    if (q.question_type === "fill_blank") {
        renderFillBlankQuestion(q);
        return;
    }

    // 场景
    $("#quiz-scene").textContent = q.scene ? `📖 ${q.scene}` : "";

    // 隐藏作文专属的表达方式
    hide($("#quiz-format"));

    // 中文
    $("#quiz-chinese").textContent = q.chinese || "";

    // 词汇提示
    if (q.hints && q.hints.length > 0) {
        show($("#quiz-hints"));
        $("#hints-content").innerHTML = q.hints
            .map(h => `<span class="hint-item">${h}</span>`)
            .join("");
        $("#hints-content").style.display = "none";
        $("#hints-toggle").textContent = "💡 词汇提示 ▾";
    } else {
        hide($("#quiz-hints"));
    }

    // 清空输入
    $("#answer-input").value = "";
    $("#answer-input").focus();

    // 关闭反馈面板
    const fbPanel = $("#feedback-area"); if (fbPanel) fbPanel.style.display = "none";

    // 提示收起
    $("#hints-toggle").onclick = () => {
        const content = $("#hints-content");
        const toggle = $("#hints-toggle");
        if (content.style.display === "none") {
            show(content);
            toggle.textContent = "💡 词汇提示 ▴";
        } else {
            hide(content);
            toggle.textContent = "💡 词汇提示 ▾";
        }
    };

    // 给新渲染的卡片加发光
    if (typeof initBorderGlowCards === 'function') {
        setTimeout(initBorderGlowCards, 100);
    }
}

// --- 填空选择题渲染（M4）---
function renderFillBlankQuestion(q) {
    // 显示 stem 含高亮空白的句子
    $("#quiz-chinese").innerHTML = (q.stem || "").replace(
        /([＿_]+)/g,
        '<span class="fillblank-blank">$1</span>'
    );
    $("#quiz-scene").textContent = q.scene ? `📖 ${q.scene}` : "";

    // 隐藏翻译题输入区，显示选择题区
    hide($("#answer-area-normal"));
    hide($("#answer-area-essay"));
    show($("#answer-area-fillblank"));

    // 渲染 4 个选项按钮
    const options = q.options || [];
    const letters = ["A", "B", "C", "D"];
    AppState.fillblankSelected = null;
    $("#fillblank-options").innerHTML = options.map((opt, i) => `
        <div class="fillblank-option" data-index="${i}">
            <span class="fillblank-option-letter">${letters[i]}</span>
            <span class="fillblank-option-text">${escapeHtml(opt)}</span>
        </div>
    `).join("");

    // 选项点击处理
    const submitBtn = $("#btn-fillblank-submit");
    submitBtn.disabled = true;
    submitBtn.textContent = "请选择答案";
    $$("#fillblank-options .fillblank-option").forEach(el => {
        el.onclick = () => {
            $$("#fillblank-options .fillblank-option").forEach(e => e.classList.remove("selected"));
            el.classList.add("selected");
            AppState.fillblankSelected = parseInt(el.dataset.index);
            submitBtn.disabled = false;
            submitBtn.textContent = "确认选择";
        };
    });

    // 提交按钮
    submitBtn.onclick = submitFillBlankAnswer;

    // 隐藏反馈
    const fbPanel = $("#feedback-area"); if (fbPanel) fbPanel.style.display = "none";
    hide($("#badge-extra"));
    hide($("#badge-difficulty"));

    // 提示处理
    if (q.hints && q.hints.length > 0) {
        show($("#quiz-hints"));
        $("#hints-content").innerHTML = q.hints.map(h => `<span class="hint-item">${h}</span>`).join("");
        hide($("#hints-content"));
        $("#hints-toggle").textContent = "💡 词汇提示 ▾";
    } else {
        hide($("#quiz-hints"));
    }
    $("#hints-toggle").onclick = () => {
        const content = $("#hints-content");
        const toggle = $("#hints-toggle");
        if (content.style.display === "none") {
            show(content);
            toggle.textContent = "💡 词汇提示 ▴";
        } else {
            hide(content);
            toggle.textContent = "💡 词汇提示 ▾";
        }
    };
}

// --- 填空选择题提交（M4）---
async function submitFillBlankAnswer() {
    if (AppState.fillblankSelected === null) return;
    const q = getCurrentQuestion();
    if (!q) return;

    const btn = $("#btn-fillblank-submit");
    btn.disabled = true;
    btn.textContent = "批改中...";

    try {
        const result = await api("/api/grade_answer", {
            method: "POST",
            body: JSON.stringify({
                question: q,
                user_answer: String(AppState.fillblankSelected),
                level: AppState.config.level,
                action: "grade",
            }),
        });
        if (!result.success || !result.feedback) throw new Error("批改失败，请重试");

        AppState.records.push({
            question: q,
            user_answer: String(AppState.fillblankSelected),
            feedback: result.feedback,
            timestamp: new Date().toISOString(),
        });
        AppState.totalAnswered++;

        // 高亮正确/错误选项
        const fb = result.feedback;
        const correctIdx = fb.correct_option;
        const selectedIdx = fb.selected_option;
        $$("#fillblank-options .fillblank-option").forEach(el => {
            const idx = parseInt(el.dataset.index);
            if (idx === correctIdx) el.classList.add("fillblank-correct");
            if (idx === selectedIdx && idx !== correctIdx) el.classList.add("fillblank-wrong");
        });

        renderFeedback(result.feedback);

        // 自动收录错题
        if (fb.score < 5 || (fb.error_parts && fb.error_parts.some(e => (e.level || "").includes("❌")))) {
            await collectWrongAnswer(q, String(AppState.fillblankSelected), fb);
        }

        await saveProgress();
    } catch (err) {
        alert(`批改失败：${err.message}`);
    } finally {
        btn.disabled = false;
        btn.textContent = "确认选择";
    }
}

// 提交答案
async function submitAnswer() {
    const userAnswer = $("#answer-input").value.trim();
    if (!userAnswer) return;

    const q = getCurrentQuestion();
    if (!q) return;

    // 禁用提交按钮
    const btnSubmit = $("#btn-submit");
    btnSubmit.disabled = true;
    btnSubmit.textContent = "批改中...";

    try {
        const result = await api("/api/grade_answer", {
            method: "POST",
            body: JSON.stringify({
                question: q,
                user_answer: userAnswer,
                level: AppState.config.level,
                action: "grade",
            }),
        });

        if (!result.success || !result.feedback) {
            throw new Error("批改失败，请重试");
        }

        // 保存答题记录
        AppState.records.push({
            question: q,
            user_answer: userAnswer,
            feedback: result.feedback,
            timestamp: new Date().toISOString(),
        });

        AppState.totalAnswered++;

        // 显示反馈
        renderFeedback(result.feedback);

        // 自动收录错题
        const fb = result.feedback;
        if (fb.score < 5 || (fb.error_parts && fb.error_parts.some(e => (e.level || "").includes("❌")))) {
            await collectWrongAnswer(q, userAnswer, fb);
        }

        // 保存进度
        await saveProgress();

    } catch (err) {
        alert(`批改失败：${err.message}`);
    } finally {
        btnSubmit.disabled = false;
        btnSubmit.textContent = "提交";
    }
}

function renderFeedback(fb) {
    const area = $("#feedback-area");
    show(area);

    // 得分颜色
    const score = fb.score || 0;
    let scoreClass = "score-low";
    if (score >= 8) scoreClass = "score-high";
    else if (score >= 5) scoreClass = "score-mid";

    let html = `
        <div class="feedback-score">
            <div class="score-number ${scoreClass}">${score.toFixed(1)}</div>
            <div class="score-label">/ 10 分</div>
        </div>
    `;

    // 正确部分
    if (fb.correct_parts && fb.correct_parts.length > 0) {
        html += `<div class="feedback-section">
            <div class="feedback-section-title feedback-correct">✅ 正确的地方</div>`;
        fb.correct_parts.forEach(p => {
            html += `<div class="feedback-item good">${p}</div>`;
        });
        html += `</div>`;
    }

    // 错误部分（区分 ⚠️ 和 ❌）
    if (fb.error_parts && fb.error_parts.length > 0) {
        html += `<div class="feedback-section">
            <div class="feedback-section-title feedback-error">❌ 需要注意的地方</div>`;
        fb.error_parts.forEach(e => {
            const level = e.level || "❌";
            const isWarning = level.includes("⚠");
            const cls = isWarning ? "bad warning" : "bad";
            html += `<div class="feedback-item ${cls}">
                <strong>${level} 错误：</strong>${e.error || ""}<br>
                <strong>正确：</strong>${e.correction || ""}<br>
                <strong>解释：</strong>${e.explanation || ""}
            </div>`;
        });
        html += `</div>`;
    }

    // 修改建议
    if (fb.suggestions) {
        html += `<div class="feedback-section">
            <div class="feedback-section-title feedback-suggestion">💡 更自然的说法</div>
            <div class="feedback-item tip">${fb.suggestions}</div>
        </div>`;
    }

    // 超纲说明
    if (fb.extra_notes) {
        html += `<div class="feedback-section">
            <div class="feedback-section-title" style="color: var(--color-warning);">📌 超纲内容拓展</div>
            <div class="feedback-item extra">${fb.extra_notes}</div>
        </div>`;
    }

    // 鼓励收尾
    if (fb.encouragement) {
        html += `<div class="feedback-section" style="text-align: center; margin-top: var(--space-md);">
            <div class="encouragement-text">${fb.encouragement}</div>
        </div>`;
    }

    $("#feedback-card").innerHTML = html;

    // 操作按钮
    const isGood = score >= 8;
    let actionHtml = "";
    if (isGood) {
        actionHtml = `
            <button class="btn btn-primary" id="btn-harder">加大难度 🔥</button>
            <button class="btn btn-secondary" id="btn-retry-same">修改重答 ✏️</button>
            <button class="btn btn-text" id="btn-next">下一题 →</button>
        `;
    } else {
        actionHtml = `
            <button class="btn btn-primary" id="btn-retry" style="background: var(--color-warning); color: white;">换道同类题再练 🔄</button>
            <button class="btn btn-secondary" id="btn-retry-same">修改重答 ✏️</button>
            <button class="btn btn-text" id="btn-skip">跳过 →</button>
        `;
    }
    $("#feedback-actions").innerHTML = actionHtml;

    // 绑定事件
    if (isGood) {
        $("#btn-harder").onclick = () => handleAction("harder");
        $("#btn-retry-same").onclick = () => retrySameQuestion();
        $("#btn-next").onclick = () => moveToNext();
    } else {
        $("#btn-retry").onclick = () => handleAction("retry");
        $("#btn-retry-same").onclick = () => retrySameQuestion();
        $("#btn-skip").onclick = () => moveToNext();
    }

    // 显示反馈
    area.style.display = "";
    area.style.animation = "none";
    area.offsetHeight; // reflow
    area.style.animation = "feedbackReveal 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)";
    refreshIcons();
}

async function handleAction(action) {
    const btnPrimary = $("#feedback-actions").querySelector(".btn-primary");
    btnPrimary.disabled = true;
    btnPrimary.textContent = action === "harder" ? "生成中..." : "换题中...";

    const q = getCurrentQuestion();

    try {
        const result = await api("/api/grade_answer", {
            method: "POST",
            body: JSON.stringify({
                question: q,
                user_answer: "",  // 不需要再批改
                level: AppState.config.level,
                action: action,
            }),
        });

        if (!result.success) {
            throw new Error("操作失败");
        }

        if (result.new_question) {
            // 把新题插入当前位置之后，并前进到新题
            AppState.questions.splice(AppState.currentIndex + 1, 0, result.new_question);
            AppState.currentIndex++;
            AppState.baseTotal++;

            const fb = $("#feedback-area"); if (fb) fb.style.display = "none";
            renderCurrentQuestion();
        }
    } catch (err) {
        alert(`操作失败：${err.message}`);
    } finally {
        btnPrimary.disabled = false;
        btnPrimary.textContent = action === "harder" ? "加大难度 🔥" : "换道同类题再练 🔄";
    }
}

function retrySameQuestion() {
    const fb = $("#feedback-area"); if (fb) fb.style.display = "none";
    $("#answer-input").value = "";
    $("#answer-input").focus();
}

function moveToNext() {
    AppState.currentIndex++;

    const fb = $("#feedback-area"); if (fb) fb.style.display = "none";

    // 重置答题区（M4：所有题型回到默认状态）
    show($("#answer-area-normal"));
    hide($("#answer-area-essay"));
    hide($("#answer-area-fillblank"));
    $("#answer-input").value = "";
    AppState.fillblankSelected = null;

    const baseCompleted = AppState.currentIndex >= AppState.baseTotal;
    const allCompleted = AppState.currentIndex >= AppState.questions.length;

    if (baseCompleted || allCompleted) {
        startEssay();
    } else {
        renderCurrentQuestion();
    }
}

// --- 进度保存 ---
async function saveProgress() {
    try {
        await api("/api/progress", {
            method: "POST",
            body: JSON.stringify({
                notes: AppState.notes,
                vocabulary: AppState.vocabulary,
                vocab_used: AppState.vocabUsed,
                level: AppState.config.level,
                questions: AppState.questions,
                current_index: AppState.currentIndex,
                records: AppState.records,
                total_answered: AppState.totalAnswered,
                base_total: AppState.baseTotal,
            }),
        });
    } catch {
        // 静默失败，不影响主流程
    }
}

// --- 恢复进度弹窗 ---
function showResumeModal(progress) {
    showScreen("main"); // 先显示主页作为背景
    show($("#modal-resume"));

    const qCount = progress.questions?.length || 0;
    const answered = progress.records?.length || 0;
    const level = progress.level || "N4";
    $("#resume-info").textContent = `上次在 ${level} 级别练习中完成了 ${answered}/${qCount} 题，是否继续？`;

    $("#btn-resume-yes").onclick = async () => {
        hide($("#modal-resume"));
        AppState.notes = progress.notes || "";
        AppState.vocabulary = progress.vocabulary || "";
        AppState.vocabUsed = progress.vocab_used || [];
        AppState.questions = progress.questions || [];
        AppState.currentIndex = progress.current_index || 0;
        AppState.records = progress.records || [];
        AppState.totalAnswered = progress.total_answered || 0;
        AppState.baseTotal = progress.base_total || AppState.questions.length;
        AppState.config.level = progress.level || AppState.config.level;
        initQuizScreen();
    };

    $("#btn-resume-no").onclick = async () => {
        hide($("#modal-resume"));
        // 清除进度
        try { await api("/api/progress", { method: "DELETE" }); } catch {}
        AppState.records = [];
        AppState.questions = [];
        AppState.currentIndex = 0;
        showMainScreen();
    };
}

// ============================================================
// 屏幕 4：总结
// ============================================================
// ============================================================
// 终极挑战：综合短文翻译
// ============================================================
async function startEssay() {
    showLoading("正在生成终极挑战作文题...");

    // 收集所有涉及的语法点
    const grammarPoints = [];
    const seen = new Set();
    for (const r of AppState.records) {
        const gp = r.question?.grammar_point;
        if (gp && !seen.has(gp)) {
            seen.add(gp);
            grammarPoints.push(gp);
        }
    }
    // 也从未答到的题目中收集
    for (const q of AppState.questions) {
        const gp = q.grammar_point;
        if (gp && !seen.has(gp)) {
            seen.add(gp);
            grammarPoints.push(gp);
        }
    }

    try {
        const result = await api("/api/generate_essay", {
            method: "POST",
            body: JSON.stringify({
                grammar_points: grammarPoints,
                level: AppState.config.level,
                notes: AppState.notes,
            }),
        });

        if (!result.success || !result.data) {
            throw new Error("作文题生成失败");
        }

        AppState.essayQuestion = result.data;
        hideLoading();
        renderEssayQuestion(result.data);
    } catch (err) {
        hideLoading();
        // 如果作文题生成失败，直接跳到总结
        alert(`作文题生成失败，跳过：${err.message}`);
        generateSummary();
    }
}

function renderEssayQuestion(essay) {
    showScreen("quiz");

    // 切换为作文模式
    const steps = $("#quiz-steps");
    if (steps) steps.innerHTML = '<span class="quiz-step-dot current" style="width:14px;height:14px;box-shadow:0 0 0 4px rgba(240,0,0,0.18)"></span>';
    $("#progress-score").textContent = `覆盖 ${essay.grammar_points_covered?.length || 0} 个语法点`;

    hide($("#badge-extra"));
    hide($("#badge-difficulty"));
    $("#grammar-tag").textContent = "📝 综合作文";

    // 场景
    $("#quiz-scene").textContent = essay.scene ? `📖 ${essay.scene}` : "";

    // 表达方式（作文独有）
    if (essay.format) {
        show($("#quiz-format"));
        $("#quiz-format").textContent = essay.format;
    } else {
        hide($("#quiz-format"));
    }

    // 要写的内容（纯内容，不含框架）
    $("#quiz-chinese").textContent = essay.chinese || "";

    // 词汇提示
    if (essay.hints && essay.hints.length > 0) {
        show($("#quiz-hints"));
        $("#hints-content").innerHTML = essay.hints
            .map(h => `<span class="hint-item">${h}</span>`)
            .join("");
        $("#hints-content").style.display = "none";
        $("#hints-toggle").textContent = "💡 词汇提示 ▾";
    } else {
        hide($("#quiz-hints"));
    }

    // 切换输入区域：隐藏单行，显示多行
    hide($("#answer-area-normal"));
    show($("#answer-area-essay"));
    $("#essay-input").value = "";
    $("#essay-input").focus();

    // 关闭反馈面板
    const fbPanel = $("#feedback-area"); if (fbPanel) fbPanel.style.display = "none";

    // 提交按钮事件
    $("#btn-essay-submit").onclick = submitEssay;
}

async function submitEssay() {
    const userAnswer = $("#essay-input").value.trim();
    if (!userAnswer) return;

    const btn = $("#btn-essay-submit");
    btn.disabled = true;
    btn.textContent = "批改中...";

    try {
        const result = await api("/api/grade_essay", {
            method: "POST",
            body: JSON.stringify({
                essay_question: AppState.essayQuestion,
                user_answer: userAnswer,
                level: AppState.config.level,
            }),
        });

        if (!result.success || !result.feedback) {
            throw new Error("批改失败");
        }

        // 保存记录
        AppState.records.push({
            question: {
                grammar_point: "综合作文",
                scene: AppState.essayQuestion.scene,
                chinese: AppState.essayQuestion.chinese,
                reference_answer: AppState.essayQuestion.reference_answer,
                is_extra: false,
                extra_level: null,
                difficulty: 4,
            },
            user_answer: userAnswer,
            feedback: result.feedback,
            timestamp: new Date().toISOString(),
            is_essay: true,
        });

        renderEssayFeedback(result.feedback);
    } catch (err) {
        alert(`批改失败：${err.message}`);
    } finally {
        btn.disabled = false;
        btn.textContent = "提交作文";
    }
}

function renderEssayFeedback(fb) {
    const area = $("#feedback-area");
    show(area);

    const score = fb.score || 0;
    let scoreClass = score >= 8 ? "score-high" : (score >= 5 ? "score-mid" : "score-low");

    let html = `
        <div class="feedback-score">
            <div class="score-number ${scoreClass}">${score.toFixed(1)}</div>
            <div class="score-label">/ 10 分（准确性 5 + 流畅度 3 + 丰富度 2）</div>        </div>
    `;

    // 用到的语法点（仅展示，不作为评分依据）
    if (fb.grammar_check && fb.grammar_check.length > 0) {
        html += `<div class="feedback-section">
            <div class="feedback-section-title">📋 你运用到的语法点</div>`;
        fb.grammar_check.forEach(gc => {
            const icon = gc.correct ? "✅" : "⚠️";
            html += `<div class="feedback-item ${gc.correct ? 'good' : 'bad'}">
                ${icon} <strong>${gc.grammar}</strong>：${gc.note}
            </div>`;
        });
        html += `</div>`;
    }

    // 正确部分
    if (fb.correct_parts && fb.correct_parts.length > 0) {
        html += `<div class="feedback-section">
            <div class="feedback-section-title feedback-correct">✅ 做得好的地方</div>`;
        fb.correct_parts.forEach(p => {
            html += `<div class="feedback-item good">${p}</div>`;
        });
        html += `</div>`;
    }

    // 建议
    if (fb.suggestions) {
        html += `<div class="feedback-section">
            <div class="feedback-section-title feedback-suggestion">💡 整体评价</div>
            <div class="feedback-item tip">${fb.suggestions}</div>
        </div>`;
    }

    // 鼓励
    if (fb.encouragement) {
        html += `<div class="feedback-section" style="text-align: center;">
            <div class="encouragement-text">${fb.encouragement}</div>
        </div>`;
    }

    $("#feedback-card").innerHTML = html;

    // 按钮：进入总结
    $("#feedback-actions").innerHTML = `
        <button class="btn btn-primary btn-full" id="btn-goto-summary">📊 查看总结报告 →</button>
    `;
    $("#btn-goto-summary").onclick = generateSummary;

    area.style.display = "";
    area.style.animation = "none"; area.offsetHeight;
    area.style.animation = "feedbackReveal 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)";
    refreshIcons();
}

// ============================================================
// 屏幕 4：总结
// ============================================================
async function generateSummary() {
    showLoading("正在生成专属复习笔记...");

    // 清除进度（已完成）
    try { await api("/api/progress", { method: "DELETE" }); } catch {}

    try {
        const result = await api("/api/generate_summary", {
            method: "POST",
            body: JSON.stringify({
                notes: AppState.notes,
                level: AppState.config.level,
                records: AppState.records,
                vocab_used: AppState.vocabUsed,
            }),
        });

        if (!result.success) {
            throw new Error("总结生成失败");
        }

        hideLoading();
        showSummaryScreen(result);

        // 弹出确认：是否保存到知识库
        showSaveLearnedModal();

    } catch (err) {
        hideLoading();
        alert(`生成总结失败：${err.message}`);
    }
}

function showSaveLearnedModal() {
    show($("#modal-save-learned"));

    $("#btn-save-yes").onclick = async () => {
        hide($("#modal-save-learned"));
        showLoading("正在保存...");
        await updateLearnedContent();
        hideLoading();
    };

    $("#btn-save-no").onclick = () => {
        hide($("#modal-save-learned"));
    };
}

async function updateLearnedContent() {
    // 从答题记录中提取语法点和得分
    const items = [];
    const seen = new Set();
    AppState.records.forEach(r => {
        const gp = r.question?.grammar_point;
        if (gp && !seen.has(gp)) {
            seen.add(gp);
            items.push({
                grammar_point: gp,
                level: r.question?.extra_level || AppState.config.level,
                score: r.feedback?.score || 0,
            });
        }
    });

    if (items.length > 0) {
        try {
            await api("/api/learned_content", {
                method: "POST",
                body: JSON.stringify({ items }),
            });
        } catch {
            // 静默失败
        }
    }

    // 同时保存今日单词到词库
    await saveVocabularyToBank();
}

// --- 保存单词到词库 ---
async function saveVocabularyToBank() {
    if (!AppState.vocabulary || !AppState.vocabulary.trim()) return;

    // 解析用户输入的单词文本
    const words = parseVocabularyText(AppState.vocabulary);
    if (words.length === 0) return;

    try {
        await api("/api/vocabulary", {
            method: "POST",
            body: JSON.stringify({ words }),
        });
    } catch {
        // 静默失败
    }
}

// --- 解析单词文本 ---
function parseVocabularyText(text) {
    const lines = text.split('\n').filter(l => l.trim());
    const words = [];

    for (const line of lines) {
        // 支持格式：日语 / 读音 / 中文意思 / 词性
        const parts = line.split('/').map(p => p.trim());
        if (parts.length >= 1 && parts[0]) {
            words.push({
                word: parts[0],
                reading: parts[1] || "",
                meaning: parts[2] || "",
                pos: parts[3] || "",
            });
        }
    }

    return words;
}

function showSummaryScreen(result) {
    showScreen("summary");

    // 统计
    const scores = AppState.records.map(r => r.feedback?.score || 0);
    const avg = scores.length > 0
        ? (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1)
        : "0";
    const high = scores.filter(s => s >= 8).length;
    const low = scores.filter(s => s < 5).length;

    let vocabUsedHtml = "";
    if (AppState.vocabUsed && AppState.vocabUsed.length > 0) {
        vocabUsedHtml = `
            <div class="stat-card wide">
                <div class="stat-label" style="font-size:12px;">📝 用到的新单词</div>
                <div style="font-size:14px; color: var(--text-primary); margin-top: 4px; line-height: 1.6;">
                    ${AppState.vocabUsed.map(w => `<span style="background: var(--color-primary-light); padding: 2px 8px; border-radius: 999px; margin: 2px; display: inline-block;">${w}</span>`).join(' ')}
                </div>
            </div>
        `;
    }

    $("#stats-card").innerHTML = `
        <div class="stat-card">
            <div class="stat-value">${AppState.records.length}</div>
            <div class="stat-label">总答题数</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${avg}</div>
            <div class="stat-label">平均分</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${high}</div>
            <div class="stat-label">高分题</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${low}</div>
            <div class="stat-label">需加强</div>
        </div>
        ${vocabUsedHtml}
    `;

    // Markdown 预览
    $("#markdown-preview").innerHTML = renderMarkdown(result.markdown || "");

    // 下载按钮
    const date = result.date || new Date().toISOString().slice(0, 10);
    $("#btn-download").onclick = () => {
        window.open(`/api/download/${date}`, "_blank");
    };

    // 再来一轮
    $("#btn-new-round").onclick = () => {
        AppState.records = [];
        AppState.questions = [];
        AppState.currentIndex = 0;
        AppState.totalAnswered = 0;
        AppState.baseTotal = 0;
        AppState.vocabUsed = [];
        showMainScreen();
    };
}

// ============================================================
// 屏幕 5 & 6：历史记录
// ============================================================
async function initHistoryScreen() {
    showLoading("加载历史记录...");

    try {
        const result = await api("/api/history");
        hideLoading();
        showScreen("history");

        const list = $("#history-list");
        const empty = $("#history-empty");

        if (!result.files || result.files.length === 0) {
            list.innerHTML = "";
            show(empty);
        } else {
            hide(empty);
            list.innerHTML = result.files.map(f => `
                <div class="history-item" data-date="${f.date}">
                    <div class="history-item-info">
                        <span class="history-item-date">📅 ${f.date}</span>
                        <span class="history-item-meta">${f.level} | ${f.record_count} 题</span>
                    </div>
                    <span class="history-item-arrow">→</span>
                </div>
            `).join("");

            // 点击查看详情
            $$(".history-item").forEach(item => {
                item.onclick = () => {
                    const date = item.dataset.date;
                    showHistoryDetail(date);
                };
            });
        }
    } catch (err) {
        hideLoading();
        alert(`加载历史失败：${err.message}`);
    }

    $("#btn-history-back").onclick = showSettingsScreen;
}

async function showHistoryDetail(date) {
    showLoading("加载记录...");

    try {
        const result = await api(`/api/history/${date}`);
        hideLoading();

        if (!result.success) {
            throw new Error("加载失败");
        }

        AppState.historyDate = date;
        showScreen("history-detail");

        const data = result.data;
        $("#detail-title").textContent = `${date} 练习记录`;

        // 如果保存了 markdown 内容，尝试加载
        if (data.summary_md) {
            try {
                // 加载 markdown 文件内容
                const mdResult = await fetch(`/api/download/${date}`);
                if (mdResult.ok) {
                    const mdText = await mdResult.text();
                    $("#detail-preview").innerHTML = renderMarkdown(mdText);
                } else {
                    showRecordFallback(data);
                }
            } catch {
                showRecordFallback(data);
            }
        } else {
            showRecordFallback(data);
        }

        $("#btn-detail-download").onclick = () => {
            window.open(`/api/download/${date}`, "_blank");
        };
    } catch (err) {
        hideLoading();
        alert(`加载详情失败：${err.message}`);
    }

    $("#btn-detail-back").onclick = initHistoryScreen;
}

function showRecordFallback(data) {
    const records = data.records || [];
    let html = `<h2>答题记录 (${records.length} 题)</h2>`;
    records.forEach((r, i) => {
        const q = r.question || {};
        const fb = r.feedback || {};
        html += `
            <h3>第 ${i + 1} 题</h3>
            <p><strong>语法点：</strong>${q.grammar_point || ""}</p>
            <p><strong>中文：</strong>${q.chinese || ""}</p>
            <p><strong>你的答案：</strong>${r.user_answer || ""}</p>
            <p><strong>参考答案：</strong>${q.reference_answer || ""}</p>
            <p><strong>得分：</strong>${fb.score || "N/A"} / 10</p>
            <hr>
        `;
    });
    $("#detail-preview").innerHTML = html;
}

// ============================================================
// Lucide 图标刷新
// ============================================================
function refreshIcons() {
    if (typeof lucide !== "undefined") lucide.createIcons();
}

// ============================================================
// 复习状态
// ============================================================
let reviewStatusEl = null;

async function loadReviewStatus() {
    try {
        const data = await api("/api/review_due");
        const dueCount = (data.due || []).length;
        const totalCount = data.total || 0;
        const bar = $("#review-status-bar");
        const inner = $("#review-card-inner");
        if (!bar || !inner) return;

        if (dueCount > 0) {
            // 列出前 3 个到期语法点
            const topItems = (data.due || []).slice(0, 3);
            const itemTags = topItems.map(i =>
                `<span class="review-tag">${i.grammar_point}<span class="review-tag-stage">第${i.review_stage || 1}轮</span></span>`
            ).join("");

            inner.innerHTML = `
                <div class="review-card-top">
                    <div class="review-card-icon"><i data-lucide="brain" style="width:22px;height:22px"></i></div>
                    <div class="review-card-text">
                        <strong>${dueCount} 个语法点待复习</strong>
                        <span>艾宾浩斯记忆系统提醒你巩固（共学习 ${totalCount} 个）</span>
                    </div>
                </div>
                <div class="review-card-tags">${itemTags}${dueCount > 3 ? `<span class="review-tag-more">+${dueCount - 3} 个</span>` : ""}</div>
                <button class="btn btn-primary btn-sm" id="btn-start-review"><i data-lucide="rocket" style="width:14px;height:14px"></i> 开始复习</button>
            `;
            bar.style.display = "";
            refreshIcons();

            $("#btn-start-review").onclick = async () => {
                showLoading("正在生成复习题目...");
                try {
                    // 收集到期语法点，生成复习题
                    const grammarPoints = (data.due || []).map(i => i.grammar_point);
                    const result = await api("/api/generate_questions", {
                        method: "POST",
                        body: JSON.stringify({
                            notes: grammarPoints.map(g => `复习：${g}`).join("\n"),
                            level: AppState.config.level,
                            vocabulary: "",
                            textbook_vocab: [],
                        }),
                    });
                    if (!result.success || !result.data) throw new Error("生成失败");
                    AppState.notes = `复习：${grammarPoints.join("、")}`;
                    AppState.vocabulary = "";
                    AppState.questions = result.data.questions || [];
                    AppState.vocabUsed = result.data.vocab_used || [];
                    AppState.currentIndex = 0; AppState.records = [];
                    AppState.totalAnswered = 0; AppState.baseTotal = AppState.questions.length;
                    hideLoading(); initQuizScreen();
                } catch (err) { hideLoading(); alert(`复习题目生成失败：${err.message}`); }
            };
        } else if (totalCount > 0) {
            inner.innerHTML = `
                <div class="review-card-top">
                    <div class="review-card-icon done"><i data-lucide="check-circle" style="width:22px;height:22px"></i></div>
                    <div class="review-card-text">
                        <strong>全部已掌握</strong>
                        <span>已学习 ${totalCount} 个语法点，暂无到期复习项</span>
                    </div>
                </div>
            `;
            bar.style.display = "";
        } else {
            bar.style.display = "none";
        }
        refreshIcons();
    } catch { /* 静默 */ }
}

// ============================================================
// 教材选择
// ============================================================
let textbookData = {};
let currentBookVocab = [];          // JLPT 卡片无词汇，保持空数组（向后兼容 POST body）
let selectedGrammarLevelId = "";    // 当前语法点选择所属的级别卷 id
let grammarModalData = [];          // 当前弹窗内展示的语法点列表

async function loadTextbookOptions() {
    try {
        const data = await api("/api/knowledge_base");
        const select = $("#textbook-select");
        if (!select) return;
        select.innerHTML = '<option value="">自由模式（不限定语法范围）</option>';
        // 只展示 jlpt_cards 教材（N5~N1）
        const jlpt = (data.textbooks || []).find(tb => tb.id === "jlpt_cards");
        const volumes = jlpt ? (jlpt.volumes || []) : [];
        volumes.forEach(vol => {
            const opt = document.createElement("option");
            opt.value = vol.id;
            opt.textContent = vol.name;  // "N5"、"N4"…
            select.appendChild(opt);
        });
        select.onchange = async () => {
            const volId = select.value;
            if (!volId) {
                // 自由模式：清空选择
                AppState.selectedGrammarPoints = [];
                selectedGrammarLevelId = "";
                updateGrammarTagsDisplay();
                updateGrammarHint();
                return;
            }
            // 切换级别时清空上一个级别的选择，保证下拉与标签一致
            if (selectedGrammarLevelId && selectedGrammarLevelId !== volId) {
                AppState.selectedGrammarPoints = [];
            }
            // 选中级别即记录，字段常驻显示（即使取消弹窗也能通过「编辑选择」重新打开）
            selectedGrammarLevelId = volId;
            updateGrammarTagsDisplay();
            updateGrammarHint();
            const vol = volumes.find(v => v.id === volId);
            await openGrammarModal(volId, vol ? vol.name : volId);
        };
        // 弹窗按钮事件（每次绑定幂等，覆盖式赋值）
        $("#btn-grammar-all").onclick = () => {
            $$("#grammar-modal-list .grammar-check-item:not(.filtered-out) input").forEach(cb => cb.checked = true);
            updateGrammarCount();
        };
        $("#btn-grammar-none").onclick = () => {
            $$("#grammar-modal-list .grammar-check-item:not(.filtered-out) input").forEach(cb => cb.checked = false);
            updateGrammarCount();
        };
        $("#grammar-search").oninput = (e) => renderGrammarCheckboxes(e.target.value);
        $("#btn-grammar-confirm").onclick = confirmGrammarSelection;
        $("#btn-grammar-cancel").onclick = () => hide($("#modal-grammar"));
        $("#btn-grammar-close").onclick = () => hide($("#modal-grammar"));
        $("#modal-grammar").onclick = (e) => {
            if (e.target === $("#modal-grammar")) hide($("#modal-grammar"));
        };
        $("#btn-edit-grammar").onclick = async () => {
            const volId = $("#textbook-select").value;
            if (!volId) return;
            const vol = volumes.find(v => v.id === volId);
            await openGrammarModal(volId, vol ? vol.name : volId);
        };
    } catch { /* 静默 */ }
}

/** 打开语法点多选弹窗，展示指定级别的全部语法点（预勾选当前已选）。 */
async function openGrammarModal(volId, levelName) {
    const modal = $("#modal-grammar");
    if (!modal) return;
    if (!textbookData[volId]) {
        try { textbookData[volId] = await api(`/api/knowledge_base/${volId}`); }
        catch { textbookData[volId] = { lessons: [] }; }
    }
    // 展平所有 lesson 的 grammar
    let points = [];
    (textbookData[volId].lessons || []).forEach(l => { points = points.concat(l.grammar || []); });
    grammarModalData = points;
    const title = $("#grammar-modal-title");
    if (title) title.textContent = `选择 ${levelName} 语法点`;
    const search = $("#grammar-search");
    if (search) search.value = "";
    renderGrammarCheckboxes("");
    show(modal);
}

/** 渲染弹窗内复选框列表，可按关键词过滤。 */
function renderGrammarCheckboxes(filterText) {
    const list = $("#grammar-modal-list");
    if (!list) return;
    const kw = (filterText || "").trim().toLowerCase();
    list.innerHTML = "";
    let visible = 0;
    grammarModalData.forEach(g => {
        const hay = (g.point || "") + " " + (g.explanation || "");
        const matches = !kw || hay.toLowerCase().includes(kw);
        if (!matches) return;
        visible++;
        const already = AppState.selectedGrammarPoints.some(p => p.point === g.point);
        const item = document.createElement("label");
        item.className = "grammar-check-item";
        item.innerHTML =
            `<input type="checkbox"${already ? " checked" : ""}>` +
            `<span class="grammar-check-body">` +
            `<span class="grammar-point">${escapeHtml(g.point)}</span>` +
            `<span class="grammar-explain">${escapeHtml(g.explanation || "")}</span>` +
            `</span>`;
        list.appendChild(item);
    });
    if (visible === 0) {
        list.innerHTML = '<p style="padding:var(--space-md) 0;text-align:center;color:var(--text-tertiary);font-size:14px;">没有匹配的语法点</p>';
    }
    updateGrammarCount();
}

/** 更新弹窗底部已选计数。 */
function updateGrammarCount() {
    const count = $("#grammar-count");
    if (!count) return;
    const checked = $$("#grammar-modal-list input[type=\"checkbox\"]:checked").length;
    count.textContent = `${checked} / ${grammarModalData.length} 已选`;
}

/** 确认弹窗选择：把勾选的语法点写入 AppState 并渲染标签。 */
function confirmGrammarSelection() {
    const checked = $$("#grammar-modal-list input[type=\"checkbox\"]:checked");
    const picked = [];
    checked.forEach(cb => {
        const point = cb.closest(".grammar-check-item").querySelector(".grammar-point").textContent;
        const g = grammarModalData.find(x => x.point === point);
        if (g) picked.push({ point: g.point, explanation: g.explanation || "" });
    });
    AppState.selectedGrammarPoints = picked;
    selectedGrammarLevelId = $("#textbook-select").value;
    hide($("#modal-grammar"));
    updateGrammarTagsDisplay();
    updateGrammarHint();
}

/** 渲染教材卡片下方的已选语法点标签（级别激活时字段常驻显示）。 */
function updateGrammarTagsDisplay() {
    const field = $("#grammar-tags-field");
    const display = $("#grammar-tags-display");
    const editBtn = $("#btn-edit-grammar");
    if (!field || !display) return;
    const pts = AppState.selectedGrammarPoints || [];
    if (!selectedGrammarLevelId) {
        // 未选择任何级别：隐藏字段
        field.style.display = "none";
        return;
    }
    field.style.display = "";
    if (pts.length > 0) {
        display.innerHTML = pts.map((g, i) =>
            `<span class="grammar-tag-chip">${escapeHtml(g.point)}` +
            `<span class="tag-remove" data-idx="${i}" title="移除">×</span></span>`
        ).join("");
    } else {
        display.innerHTML = '<span class="grammar-tags-empty">未选择语法点</span>';
    }
    if (editBtn) editBtn.style.display = "";
    display.querySelectorAll(".tag-remove").forEach(el => {
        el.onclick = (e) => {
            e.stopPropagation();
            AppState.selectedGrammarPoints.splice(parseInt(el.dataset.idx, 10), 1);
            updateGrammarTagsDisplay();
            updateGrammarHint();
        };
    });
}

/** 更新教材卡片底部提示文字。 */
function updateGrammarHint() {
    const hint = $("#textbook-hint");
    if (!hint) return;
    const count = (AppState.selectedGrammarPoints || []).length;
    if (!selectedGrammarLevelId) {
        hint.textContent = "选择级别后可指定具体的语法点范围";
    } else if (count > 0) {
        hint.textContent = `已选择 ${count} 个语法点，出题将聚焦这些知识点`;
    } else {
        hint.textContent = "已选择级别，可点击「编辑选择」指定语法点（不指定则出题不受语法点限制）";
    }
}

// ============================================================
// 错题本
// ============================================================
async function collectWrongAnswer(question, userAnswer, feedback) {
    const errorTypes = [];
    if (feedback.error_parts) feedback.error_parts.forEach(e => {
        if ((e.level || "").includes("❌")) errorTypes.push("核心错误");
        else if ((e.level || "").includes("⚠")) errorTypes.push("小问题");
    });
    const item = { id: Date.now(), grammar_point: question.grammar_point || "", question: question, user_answer: userAnswer, feedback: feedback, score: feedback.score || 0, error_types: errorTypes, added_at: new Date().toISOString().slice(0, 10), reviewed_count: 0, last_reviewed: null, mastered: false };
    try { await api("/api/wrong_book", { method: "POST", body: JSON.stringify({ items: [item] }) }); } catch { /* 静默 */ }
}

async function initWrongBookScreen() {
    showLoading("加载错题本...");
    try {
        const result = await api("/api/wrong_book"); hideLoading(); showScreen("wrong-book");
        const items = result.items || [];
        if (items.length === 0) { $("#wrong-list").innerHTML = ""; show($("#wrong-empty")); hide($("#wrong-stats")); }
        else {
            hide($("#wrong-empty"));

            // 按语法点分组
            const groups = new Map();
            for (const item of items) {
                const gp = item.grammar_point || "综合";
                if (!groups.has(gp)) groups.set(gp, []);
                groups.get(gp).push(item);
            }

            const totalGroups = groups.size;
            const totalItems = items.length;
            const activeGroups = [...groups.values()].filter(g => g.some(i => !i.mastered)).length;
            const activeItems = items.filter(i => !i.mastered).length;
            $("#wrong-stats").innerHTML = `共 <strong>${totalGroups}</strong> 个语法点（<strong>${totalItems}</strong> 题），未掌握 <strong>${activeGroups}</strong> 个${activeItems > 0 ? `，已掌握 ${totalItems - activeItems} 题` : ""}`;
            show($("#wrong-stats"));

            let html = "";
            for (const [grammar, groupItems] of groups) {
                const avgScore = (groupItems.reduce((s, i) => s + (i.score || 0), 0) / groupItems.length).toFixed(1);
                const allMastered = groupItems.every(i => i.mastered);
                const errorTypes = [...new Set(groupItems.flatMap(i => i.error_types || []))];

                html += `<div class="wrong-group${allMastered ? " wrong-group-mastered" : ""}">
                    <div class="wrong-group-header">
                        <div class="wrong-group-info">
                            <span class="wrong-group-grammar">${grammar}</span>
                            <span class="wrong-group-meta">${groupItems.length} 题 · 均分 ${avgScore}</span>
                            ${errorTypes.length > 0 ? `<span class="wrong-group-errors">${errorTypes.join(" · ")}</span>` : ""}
                        </div>
                        <i data-lucide="chevron-down" style="width:16px;height:16px;color:var(--text-tertiary);transition:transform 0.25s"></i>
                    </div>
                    <div class="wrong-group-body" style="display:none">`;

                for (const item of groupItems) {
                    const sc = item.score >= 5 ? "mid" : "low";
                    html += `<div class="wrong-item${item.mastered ? " wrong-item-mastered" : ""}" data-id="${item.id}">
                        <div class="wrong-item-header">
                            <span class="wrong-item-date">${item.added_at}</span>
                            <span class="wrong-item-score ${sc}">${item.score}分</span>
                        </div>
                        <div class="wrong-item-preview">${item.error_types.length > 0 ? "错误类型：" + item.error_types.join("、") : (item.feedback?.suggestions || "").slice(0, 50)}</div>
                    </div>`;
                }

                html += `</div></div>`;
            }
            $("#wrong-list").innerHTML = html;
            refreshIcons();

            // 点击组头展开/折叠
            $$(".wrong-group-header").forEach(header => {
                header.onclick = () => {
                    const group = header.closest(".wrong-group");
                    const body = group.querySelector(".wrong-group-body");
                    const icon = header.querySelector("i");
                    const isOpen = body.style.display !== "none";
                    body.style.display = isOpen ? "none" : "";
                    if (icon) icon.style.transform = isOpen ? "" : "rotate(180deg)";
                };
            });

            // 点击具体错题查看详情
            $$(".wrong-item").forEach(el => {
                el.onclick = (e) => {
                    e.stopPropagation();
                    const id = parseInt(el.dataset.id);
                    const item = items.find(i => i.id === id);
                    if (item) showWrongDetail(item);
                };
            });
        }
    } catch (err) { hideLoading(); alert(`加载失败：${err.message}`); }
    $("#btn-wrong-back").onclick = showSettingsScreen;
}

function showWrongDetail(item) {
    showScreen("wrong-book"); hide($("#wrong-list")); hide($("#wrong-stats")); hide($("#wrong-empty"));
    const fb = item.feedback || {}; const errors = fb.error_parts || [];
    const errorHtml = errors.length > 0 ? errors.map(e => `<div class="wrong-detail-text error"><strong>${e.level || ""} ${e.error || ""}</strong><br>正确：${e.correction || ""}<br>${e.explanation || ""}</div>`).join("") : "<p>暂无详细错误信息</p>";
    const correctHtml = (fb.correct_parts || []).length > 0 ? fb.correct_parts.map(c => `<div class="wrong-detail-text correct">${c}</div>`).join("") : "";
    const html = `<div class="wrong-detail">
        <div class="wrong-detail-section"><div class="wrong-detail-label">📖 原题</div><div class="wrong-detail-text">${item.question?.chinese || ""}</div></div>
        <div class="wrong-detail-section"><div class="wrong-detail-label">✏️ 你的答案</div><div class="wrong-detail-text error">${item.user_answer || ""}</div></div>
        <div class="wrong-detail-section"><div class="wrong-detail-label">✅ 参考答案</div><div class="wrong-detail-text correct">${item.question?.reference_answer || ""}</div></div>
        ${correctHtml ? `<div class="wrong-detail-section"><div class="wrong-detail-label">✅ 做得对的地方</div>${correctHtml}</div>` : ""}
        <div class="wrong-detail-section"><div class="wrong-detail-label">❌ 需要注意</div>${errorHtml}</div>
        ${fb.suggestions ? `<div class="wrong-detail-section"><div class="wrong-detail-label">💡 建议</div><div class="wrong-detail-text">${fb.suggestions}</div></div>` : ""}
    </div>
    <div class="wrong-actions">
        <button class="btn btn-primary" id="btn-wrong-retry">🔄 重新练习</button>
        <button class="btn btn-secondary" id="btn-wrong-mastered">✅ 标记已掌握</button>
        <button class="btn btn-text" id="btn-wrong-back-list">← 返回列表</button>
    </div>`;
    const container = document.createElement("div"); container.id = "wrong-detail-container"; container.innerHTML = html;
    const wrongScreen = $("#screen-wrong-book"); if (wrongScreen) wrongScreen.appendChild(container);
    $("#btn-wrong-retry").onclick = () => rePracticeWrong(item);
    $("#btn-wrong-mastered").onclick = () => markWrongMastered(item);
    $("#btn-wrong-back-list").onclick = () => { const dc = $("#wrong-detail-container"); if (dc) dc.remove(); show($("#wrong-list")); initWrongBookScreen(); };
}

async function rePracticeWrong(item) {
    const dc = $("#wrong-detail-container"); if (dc) dc.remove();
    showLoading("正在生成练习题目...");
    try {
        const result = await api("/api/grade_answer", { method: "POST", body: JSON.stringify({ question: { grammar_point: item.grammar_point }, user_answer: "", level: AppState.config.level, action: "retry" }) });
        if (!result.success || !result.new_question) throw new Error("生成失败");
        await api("/api/wrong_book", { method: "POST", body: JSON.stringify({ items: [{ id: item.id, reviewed_count: (item.reviewed_count || 0) + 1, last_reviewed: new Date().toISOString().slice(0, 10) }] }) });
        hideLoading(); AppState.questions = [result.new_question]; AppState.currentIndex = 0; AppState.records = []; AppState.totalAnswered = 0; AppState.baseTotal = 1;
        initQuizScreen();
    } catch (err) { hideLoading(); alert(`生成失败：${err.message}`); }
}

async function markWrongMastered(item) {
    await api("/api/wrong_book", { method: "POST", body: JSON.stringify({ items: [{ id: item.id, mastered: true }] }) });
    const dc = $("#wrong-detail-container"); if (dc) dc.remove(); show($("#wrong-list")); initWrongBookScreen();
}

// ============================================================
// 初始化
// ============================================================
let clickSparkInstance = null;

function init() {
    // 提交按钮
    $("#btn-submit").onclick = submitAnswer;

    // 回车提交
    $("#answer-input").onkeydown = (e) => {
        if (e.key === "Enter" && !$("#btn-submit").disabled) {
            submitAnswer();
        }
    };

    // 答题页面返回按钮
    const quizBack = $("#btn-quiz-back");
    if (quizBack) quizBack.onclick = showMainScreen;

    // ====== ReactBits 动效 ======
    // ClickSpark — 全局点击火花
    if (typeof createClickSpark === 'function') {
        clickSparkInstance = createClickSpark({
            sparkColor: getComputedStyle(document.documentElement).getPropertyValue('--color-primary').trim() || '#F00000',
            sparkCount: 6,
            sparkRadius: 18,
            duration: 350,
        });
    }

    // 所有按钮加弹簧按压
    document.addEventListener('click', e => {
        const btn = e.target.closest('.btn');
        if (btn && typeof springPress === 'function') {
            springPress(btn);
        }
    });

    // 首页公告卡片 → 公告弹窗
    const announceCard = $("#guide-announce");
    if (announceCard) announceCard.onclick = showAnnounceModal;

    // 启动
    initGuideScreen();
}

// ============================================================
// Dock 导航栏
// ============================================================
function setDockActive(screen) {
    document.querySelectorAll('.dock-item').forEach(item => {
        item.classList.toggle('active', item.dataset.screen === screen);
    });
}

function initDock() {
    const panel = $("#dock-panel");
    if (!panel) return;

    const items = panel.querySelectorAll('.dock-item');
    const baseSize = 48;
    const maxSize = 68;
    const distance = 120;

    panel.addEventListener('mousemove', e => {
        const panelRect = panel.getBoundingClientRect();
        const mouseX = e.clientX;

        items.forEach(item => {
            const rect = item.getBoundingClientRect();
            const itemCenter = rect.left + rect.width / 2;
            const dist = Math.abs(mouseX - itemCenter);
            const scale = dist < distance
                ? baseSize + (maxSize - baseSize) * Math.pow(1 - dist / distance, 2)
                : baseSize;
            item.style.width = scale + 'px';
            item.style.height = scale + 'px';
        });
    });

    panel.addEventListener('mouseleave', () => {
        items.forEach(item => {
            item.style.width = baseSize + 'px';
            item.style.height = baseSize + 'px';
        });
    });

    // 点击导航
    items.forEach(item => {
        item.addEventListener('click', () => {
            const screen = item.dataset.screen;
            switch (screen) {
                case 'guide': showGuideScreen(); break;
                case 'main': showMainScreen(); break;
                case 'qa': showQaScreen(); break;
                case 'settings': showSettingsScreen(); break;
            }
        });
    });
}

// 首页（引导页）
function showGuideScreen() {
    showScreen("guide");
    setDockActive("guide");
    $("#btn-guide-start").onclick = async () => {
        const data = await loadConfig();
        if (data && data.has_api_key) {
            initMainScreen();
        } else {
            initSetupScreen();
        }
    };
}

// 设置页面
function showSettingsScreen() {
    showScreen("settings");
    setDockActive("settings");

    // hero 区域
    const heroIcon = $("#screen-settings .setup-icon-wrap");
    if (heroIcon) heroIcon.innerHTML = '<i data-lucide="settings" style="width:40px;height:40px"></i>';
    const heroTitle = $("#screen-settings .setup-hero h1");
    if (heroTitle) heroTitle.textContent = "设置";
    const heroDesc = $("#screen-settings .setup-desc");
    if (heroDesc) heroDesc.textContent = "API Key · 学习目标 · 学习数据 · 外观";

    const card = $("#screen-settings .setup-card");
    if (!card) return;
    card.innerHTML = `
        <div class="settings-body">
            <!-- 左列：学习数据（宽） -->
            <div class="settings-learning">
                <div class="settings-section-title">📊 学习数据</div>
                <div class="checkin-calendar card" id="checkin-calendar" style="margin-bottom:var(--space-md)">
                    <div class="checkin-cal-header">
                        <div class="checkin-stats-row">
                            <div class="checkin-stat-badge">
                                <i data-lucide="flame" style="width:22px;height:22px;color:var(--color-warning)"></i>
                                <div class="checkin-stat-info">
                                    <span class="checkin-stat-num" id="cal-streak-num">--</span>
                                    <span class="checkin-stat-label">连续学习</span>
                                </div>
                            </div>
                            <div class="checkin-stat-badge">
                                <i data-lucide="calendar-check" style="width:22px;height:22px;color:var(--color-primary)"></i>
                                <div class="checkin-stat-info">
                                    <span class="checkin-stat-num" id="cal-month-num">--</span>
                                    <span class="checkin-stat-label">本月累计</span>
                                </div>
                            </div>
                        </div>
                        <div class="checkin-month-nav">
                            <button class="checkin-nav-btn" id="cal-prev-month"><i data-lucide="chevron-left" style="width:16px;height:16px"></i></button>
                            <span class="checkin-month-label" id="cal-month-label">2026年8月</span>
                            <button class="checkin-nav-btn" id="cal-next-month"><i data-lucide="chevron-right" style="width:16px;height:16px"></i></button>
                        </div>
                    </div>
                    <div class="checkin-weekdays">
                        <span>日</span><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span>
                    </div>
                    <div class="checkin-grid" id="checkin-grid"></div>
                </div>
                <div class="review-plan card" id="review-plan" style="margin-bottom:var(--space-md)">
                    <div class="review-plan-header">
                        <i data-lucide="brain" style="width:18px;height:18px;color:var(--color-primary)"></i>
                        <span>复习计划</span>
                        <span class="review-plan-badge" id="review-plan-badge" style="display:none"></span>
                    </div>
                    <div class="review-plan-list" id="review-plan-list">
                        <p class="review-plan-empty">加载中...</p>
                    </div>
                </div>
                <div class="settings-list">
                    <div class="settings-item clickable" id="settings-wrong">
                        <div class="settings-item-info">
                            <div class="settings-item-title"><i data-lucide="edit-3" style="width:18px;height:18px"></i> 错题本</div>
                            <div class="settings-item-desc">查看和复习做错的题目</div>
                        </div>
                        <i data-lucide="chevron-right" style="width:16px;height:16px;color:var(--text-tertiary)"></i>
                    </div>
                    <div class="settings-item clickable" id="settings-history">
                        <div class="settings-item-info">
                            <div class="settings-item-title"><i data-lucide="clipboard-list" style="width:18px;height:18px"></i> 历史记录</div>
                            <div class="settings-item-desc">查看过往练习记录</div>
                        </div>
                        <i data-lucide="chevron-right" style="width:16px;height:16px;color:var(--text-tertiary)"></i>
                    </div>
                    <div class="settings-item">
                        <div class="settings-item-info">
                            <div class="settings-item-title"><i data-lucide="database" style="width:18px;height:18px"></i> 学习数据</div>
                            <div class="settings-item-desc">导出全部学习数据，更新版本或换机时导入恢复</div>
                        </div>
                        <div class="settings-data-actions">
                            <button class="btn btn-secondary btn-sm" id="btn-data-export"><i data-lucide="download" style="width:14px;height:14px"></i> 导出</button>
                            <button class="btn btn-secondary btn-sm" id="btn-data-import"><i data-lucide="upload" style="width:14px;height:14px"></i> 导入</button>
                            <input type="file" id="data-import-input" accept=".json,application/json" style="display:none">
                        </div>
                    </div>
                </div>
            </div>
            <!-- 右列：功能设置（窄） -->
            <div class="settings-func">
                <div class="settings-section-title">⚙️ 功能设置</div>
                <div class="settings-list">
                    <div class="settings-item" style="flex-direction:column;align-items:stretch;gap:var(--space-md);padding-top:var(--space-sm)">
                        <div class="settings-item-title" style="margin-bottom:2px"><i data-lucide="key" style="width:18px;height:18px;color:var(--color-primary)"></i> DeepSeek API Key</div>
                        <input type="password" id="settings-apikey-input" class="input" placeholder="sk-..." autocomplete="off" style="width:100%">
                        <div class="settings-item-desc">在 <a href="https://platform.deepseek.com/api_keys" target="_blank" rel="noopener">DeepSeek 平台</a> 获取，Key 仅保存在本地，不会上传</div>
                        <div style="display:flex;gap:8px;justify-content:flex-end">
                            <button class="btn btn-primary btn-sm" id="btn-save-apikey">保存</button>
                        </div>
                        <p id="apikey-error" class="error-text" style="display:none;"></p>
                    </div>
                    <div class="settings-item">
                        <div class="settings-item-info">
                            <div class="settings-item-title"><i data-lucide="target" style="width:18px;height:18px"></i> 学习目标</div>
                        </div>
                        <select class="input" id="settings-learning-goal" style="width:104px;flex-shrink:0;padding:6px 8px;font-size:13px">
                            <option value="">不限</option>
                            <option value="兴趣">兴趣</option>
                            <option value="旅游">旅游</option>
                            <option value="JLPT">JLPT</option>
                            <option value="高考">高考</option>
                            <option value="考研">考研</option>
                        </select>
                    </div>
                    <div class="settings-item">
                        <div class="settings-item-info">
                            <div class="settings-item-title"><i data-lucide="cpu" style="width:18px;height:18px"></i> 使用模型</div>
                            <div class="settings-item-desc">当前仅支持 DeepSeek V4</div>
                        </div>
                        <span style="font-size:12px;font-weight:700;color:var(--color-primary);background:var(--color-primary-tint,#FFEBEB);padding:3px 12px;border-radius:var(--radius-full);white-space:nowrap">开发中</span>
                    </div>
                    <div class="settings-item" style="flex-direction:column;align-items:stretch;gap:var(--space-sm);padding-top:var(--space-sm)">
                        <div class="settings-item-title"><i data-lucide="sun-moon" style="width:18px;height:18px"></i> 显示模式</div>
                        <div class="theme-toggle">
                            <button class="theme-option" data-theme-val="light">☀️ 浅色</button>
                            <button class="theme-option" data-theme-val="auto">🔄 自动</button>
                            <button class="theme-option" data-theme-val="dark">🌙 深色</button>
                        </div>
                    </div>
                    <div class="settings-item">
                        <div class="settings-item-info">
                            <div class="settings-item-title"><i data-lucide="trash-2" style="width:18px;height:18px"></i> 清除数据</div>
                            <div class="settings-item-desc">清除 API Key、答题进度、知识库等所有本地数据</div>
                        </div>
                        <button class="btn btn-secondary btn-sm" id="btn-clear-data">清除</button>
                    </div>
                    <div class="settings-item clickable" id="settings-privacy">
                        <div class="settings-item-info">
                            <div class="settings-item-title"><i data-lucide="shield" style="width:18px;height:18px"></i> 隐私政策</div>
                            <div class="settings-item-desc">了解我们如何保护你的数据</div>
                        </div>
                        <i data-lucide="chevron-right" style="width:16px;height:16px;color:var(--text-tertiary)"></i>
                    </div>
                    <div class="settings-item clickable" id="settings-guide">
                        <div class="settings-item-info">
                            <div class="settings-item-title"><i data-lucide="book-open" style="width:18px;height:18px"></i> 使用说明</div>
                            <div class="settings-item-desc">快速上手 KOTOBA·AI 的使用流程</div>
                        </div>
                        <i data-lucide="chevron-right" style="width:16px;height:16px;color:var(--text-tertiary)"></i>
                    </div>
                    <div class="settings-item clickable" id="settings-roadmap">
                        <div class="settings-item-info">
                            <div class="settings-item-title"><i data-lucide="map" style="width:18px;height:18px"></i> 开发路线图</div>
                            <div class="settings-item-desc">查看未来版本的开发计划</div>
                        </div>
                        <i data-lucide="chevron-right" style="width:16px;height:16px;color:var(--text-tertiary)"></i>
                    </div>
                </div>
            </div>
        </div>
    `;
    refreshIcons();

    // 填充当前 API Key
    const apikeyInput = $("#settings-apikey-input");
    if (apikeyInput) apikeyInput.value = AppState.config.api_key || "";

    // 保存按钮
    const saveBtn = $("#btn-save-apikey");
    if (saveBtn) saveBtn.onclick = async () => {
        const key = apikeyInput.value.trim();
        if (!key) {
            showError("apikey-error", "请输入 API Key");
            return;
        }
        if (!key.startsWith("sk-")) {
            showError("apikey-error", "API Key 格式不正确，应以 sk- 开头");
            return;
        }
        try {
            await saveConfig({ api_key: key });
            hide($("#apikey-error"));
            apikeyInput.value = key;
            alert("API Key 已保存");
        } catch {
            showError("apikey-error", "保存失败，请检查网络连接");
        }
    };

    // 学习目标下拉（M4）
    const goalSelect = $("#settings-learning-goal");
    if (goalSelect) {
        goalSelect.value = AppState.config.learning_goal || "";
        goalSelect.onchange = async () => {
            try {
                await saveConfig({ learning_goal: goalSelect.value });
                AppState.config.learning_goal = goalSelect.value;
            } catch { /* 静默 */ }
        };
    }

    // 主题切换按钮（作用域限定在设置页）
    const currentTheme = getTheme();
    document.querySelectorAll('#screen-settings .theme-option').forEach(btn => {
        if (btn.dataset.themeVal === currentTheme) btn.classList.add('active');
        btn.onclick = () => {
            setTheme(btn.dataset.themeVal);
            document.querySelectorAll('#screen-settings .theme-option').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        };
    });

    // 清除数据按钮
    const clearBtn = $("#btn-clear-data");
    if (clearBtn) {
        clearBtn.onclick = async () => {
            if (confirm("确定要清除所有本地数据吗？此操作不可撤销。")) {
                try {
                    await api("/api/reset", { method: "POST" });
                    alert("数据已清除。软件将返回初始状态。");
                    location.reload();
                } catch { alert("清除失败"); }
            }
        };
    }

    // 错题本入口（M4：从个人页迁移）
    const wrongEntry = $("#settings-wrong");
    if (wrongEntry) wrongEntry.onclick = initWrongBookScreen;

    // 历史记录入口（M4：从个人页迁移）
    const historyEntry = $("#settings-history");
    if (historyEntry) historyEntry.onclick = initHistoryScreen;

    // 学习数据导出 / 导入
    const exportBtn = $("#btn-data-export");
    if (exportBtn) exportBtn.onclick = async () => {
        // pywebview 原生环境：弹出系统保存对话框，让用户自选导出位置
        if (window.pywebview && window.pywebview.api
            && typeof window.pywebview.api.export_user_data_native === "function") {
            try {
                const r = await window.pywebview.api.export_user_data_native();
                if (r && r.success) {
                    alert("学习数据已导出到：\n" + r.path);
                }
                // 用户取消或不成功则不打扰
            } catch (e) {
                alert("导出失败：" + ((e && e.message) || e));
            }
            return;
        }
        // 浏览器模式降级：直接触发下载
        window.open("/api/data/export", "_blank");
    };

    const importBtn = $("#btn-data-import");
    const importInput = $("#data-import-input");
    if (importBtn && importInput) {
        importBtn.onclick = () => importInput.click();
        importInput.onchange = async () => {
            const file = importInput.files && importInput.files[0];
            importInput.value = "";
            if (!file) return;
            if (!/\.json$/i.test(file.name)) {
                alert("请选择 KOTOBA·AI 导出的 .json 备份文件");
                return;
            }
            let parsed;
            try {
                parsed = JSON.parse(await file.text());
            } catch {
                alert("文件解析失败，不是有效的备份文件");
                return;
            }
            if (!parsed || parsed.app !== "KOTOBA-AI") {
                alert("这不是 KOTOBA·AI 的备份文件");
                return;
            }
            if (!confirm("导入将把备份中的学习数据合并到本机（同名记录将被覆盖），是否继续？")) return;
            try {
                const res = await fetch("/api/data/import", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(parsed),
                });
                const j = await res.json();
                if (j.success) {
                    alert(j.message || "导入成功，正在刷新…");
                    location.reload();
                } else {
                    alert(j.error || "导入失败");
                }
            } catch {
                alert("导入失败，请重试");
            }
        };
    }

    // 隐私政策
    const privacyBtn = $("#settings-privacy");
    if (privacyBtn) privacyBtn.onclick = showPrivacyScreen;

    // 使用说明
    const guideBtn = $("#settings-guide");
    if (guideBtn) guideBtn.onclick = showGuideModal;

    // 开发路线图
    const roadmapBtn = $("#settings-roadmap");
    if (roadmapBtn) roadmapBtn.onclick = showRoadmapModal;

    // 加载打卡数据并渲染日历（M4：从个人页迁移）
    renderCheckinCalendar();

    // 加载复习计划（M4：从个人页迁移）
    loadReviewPlan();

    // 版本行
    const versionRow = document.createElement("div");
    versionRow.className = "settings-item";
    versionRow.style.borderTop = "1px solid var(--border-light)";
    versionRow.style.justifyContent = "center";
    versionRow.innerHTML = `
        <div class="settings-item-info" style="align-items:center">
            <span style="font-size:12px;color:var(--text-tertiary)">KOTOBA·AI Beta v4.0 · 罗盘更新 · GPL-3.0</span>
        </div>
    `;
    card.appendChild(versionRow);

    // 返回按钮（不在 card 内，始终安全）
    const backBtn = $("#btn-settings-back");
    if (backBtn) {
        backBtn.style.display = "";
        backBtn.onclick = showMainScreen;
    }
}


// 隐私政策弹窗
function showPrivacyScreen() {
    show($("#modal-privacy"));
    refreshIcons();
    $("#btn-privacy-close").onclick = () => hide($("#modal-privacy"));
    // 点击遮罩关闭
    $("#modal-privacy").onclick = (e) => {
        if (e.target === $("#modal-privacy")) hide($("#modal-privacy"));
    };
}

// 使用说明弹窗
function showGuideModal() {
    show($("#modal-guide"));
    refreshIcons();
    $("#btn-guide-close").onclick = () => hide($("#modal-guide"));
    $("#modal-guide").onclick = (e) => {
        if (e.target === $("#modal-guide")) hide($("#modal-guide"));
    };
}

// 开发路线图弹窗
function showRoadmapModal() {
    show($("#modal-roadmap"));
    refreshIcons();
    $("#btn-roadmap-close").onclick = () => hide($("#modal-roadmap"));
    $("#modal-roadmap").onclick = (e) => {
        if (e.target === $("#modal-roadmap")) hide($("#modal-roadmap"));
    };
}

// 公告弹窗
function showAnnounceModal() {
    show($("#modal-announce"));
    refreshIcons();
    $("#btn-announce-close").onclick = () => hide($("#modal-announce"));
    $("#modal-announce").onclick = (e) => {
        if (e.target === $("#modal-announce")) hide($("#modal-announce"));
    };
}

// ============================================================
// 打卡记录
// ============================================================
let checkinData = null;
let calYear = new Date().getFullYear();
let calMonth = new Date().getMonth() + 1; // 0-based → 1-based

async function loadCheckinData() {
    try {
        checkinData = await api("/api/checkin");
    } catch {
        checkinData = { dates: [], streak: 0, monthly_count: 0, monthly_dates: [] };
    }
    return checkinData;
}

// 主页右侧迷你打卡卡片
async function loadCheckinMini() {
    const data = await loadCheckinData();
    const streakEl = $("#checkin-streak-num");
    const monthEl = $("#checkin-month-num");
    const dotsEl = $("#checkin-mini-dots");
    if (!streakEl || !monthEl || !dotsEl) return;

    streakEl.textContent = data.streak || "0";
    monthEl.textContent = data.monthly_count || "0";

    // 近 7 天的小圆点
    const today = new Date();
    let dotsHtml = "";
    for (let i = 6; i >= 0; i--) {
        const d = new Date(today);
        d.setDate(d.getDate() - i);
        const dateStr = d.toISOString().slice(0, 10);
        const active = (data.dates || []).includes(dateStr);
        const weekday = ["日","一","二","三","四","五","六"][d.getDay()];
        dotsHtml += `<span class="checkin-dot${active ? " active" : ""}" title="${dateStr} 周${weekday}">${active ? '<i data-lucide="check" style="width:10px;height:10px"></i>' : ""}</span>`;
    }
    dotsEl.innerHTML = dotsHtml;
    if (typeof lucide !== "undefined") lucide.createIcons();
}

// 个人页完整日历
let calActiveSet = new Set();

async function renderCheckinCalendar(monthOffset = 0) {
    const data = await loadCheckinData();
    calActiveSet = new Set(data.dates || []);

    // 计算目标月份
    const now = new Date();
    const target = new Date(now.getFullYear(), now.getMonth() + monthOffset, 1);
    calYear = target.getFullYear();
    calMonth = target.getMonth() + 1;

    // 更新标题
    const label = $("#cal-month-label");
    if (label) label.textContent = `${calYear}年${calMonth}月`;

    // 本月活跃天数
    const monthPrefix = `${calYear}-${String(calMonth).padStart(2, "0")}`;
    const monthActive = (data.dates || []).filter(d => d.startsWith(monthPrefix));

    // 更新统计数字
    const streakEl = $("#cal-streak-num");
    const monthEl = $("#cal-month-num");
    if (streakEl) streakEl.textContent = data.streak || "0";
    if (monthEl) monthEl.textContent = monthActive.length;

    // 渲染日历网格
    const grid = $("#checkin-grid");
    if (!grid) return;

    const firstDay = new Date(calYear, calMonth - 1, 1).getDay(); // 0=周日
    const daysInMonth = new Date(calYear, calMonth, 0).getDate();

    let html = "";
    // 填充前面的空白格
    for (let i = 0; i < firstDay; i++) {
        html += '<div class="checkin-day empty"></div>';
    }
    // 日期格
    for (let day = 1; day <= daysInMonth; day++) {
        const dateStr = `${calYear}-${String(calMonth).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
        const isActive = calActiveSet.has(dateStr);
        const isToday = dateStr === new Date().toISOString().slice(0, 10);
        let cls = "checkin-day";
        if (isToday) cls += " today";
        if (isActive) cls += " active";
        html += `<div class="${cls}">${isActive ? '<span class="checkin-day-num">' + day + '</span>' : day}</div>`;
    }
    grid.innerHTML = html;

    // 导航按钮
    const prevBtn = $("#cal-prev-month");
    const nextBtn = $("#cal-next-month");
    if (prevBtn) prevBtn.onclick = () => renderCheckinCalendar(monthOffset - 1);
    if (nextBtn) {
        // 不能超过当前月份
        const isCurrentOrFuture = (calYear === now.getFullYear() && calMonth >= now.getMonth() + 1) || calYear > now.getFullYear();
        nextBtn.disabled = isCurrentOrFuture;
        if (!isCurrentOrFuture) nextBtn.onclick = () => renderCheckinCalendar(monthOffset + 1);
    }
}

// 个人页复习计划
async function loadReviewPlan() {
    try {
        const data = await api("/api/review_due");
        const due = data.due || [];
        const total = data.total || 0;
        const badge = $("#review-plan-badge");
        const list = $("#review-plan-list");
        if (!list) return;

        if (due.length > 0) {
            if (badge) { badge.textContent = `${due.length} 个待复习`; badge.style.display = ""; }
            const items = due.slice(0, 5);
            list.innerHTML = items.map(i => {
                const stageLabel = i.review_stage ? `第${i.review_stage}轮` : "新学";
                const lastScore = i.history_scores?.length ? i.history_scores[i.history_scores.length - 1].toFixed(1) : "--";
                return `<div class="review-plan-item" data-grammar="${i.grammar_point}">
                    <div class="review-plan-item-left">
                        <span class="review-plan-grammar">${i.grammar_point}</span>
                        <span class="review-plan-meta">${stageLabel} · 上次得分 ${lastScore} · ${i.review_interval || 0} 天间隔</span>
                    </div>
                    <i data-lucide="play-circle" style="width:18px;height:18px;color:var(--color-primary)"></i>
                </div>`;
            }).join("") + (due.length > 5 ? `<p class="review-plan-more">还有 ${due.length - 5} 个语法点待复习...</p>` : "");
        } else if (total > 0) {
            list.innerHTML = `<p class="review-plan-empty">✅ 全部语法点已掌握，暂无到期复习</p>`;
            if (badge) badge.style.display = "none";
        } else {
            list.innerHTML = `<p class="review-plan-empty">完成首次练习后，艾宾浩斯记忆系统将自动安排复习</p>`;
            if (badge) badge.style.display = "none";
        }
        refreshIcons();

        // 点击复习项
        $$(".review-plan-item").forEach(el => {
            el.onclick = async () => {
                const gp = el.dataset.grammar;
                showLoading(`正在为「${gp}」生成复习题...`);
                try {
                    const result = await api("/api/generate_questions", {
                        method: "POST",
                        body: JSON.stringify({
                            notes: `复习：${gp}`,
                            level: AppState.config.level,
                            vocabulary: "",
                            textbook_vocab: [],
                        }),
                    });
                    if (!result.success || !result.data) throw new Error("生成失败");
                    AppState.notes = `复习：${gp}`; AppState.vocabulary = "";
                    AppState.questions = result.data.questions || [];
                    AppState.vocabUsed = result.data.vocab_used || [];
                    AppState.currentIndex = 0; AppState.records = [];
                    AppState.totalAnswered = 0; AppState.baseTotal = AppState.questions.length;
                    hideLoading(); initQuizScreen();
                } catch (err) { hideLoading(); alert(`复习题生成失败：${err.message}`); }
            };
        });
    } catch { /* 静默 */ }
}

// ============================================================
// 答疑（QA）页面 — M2
// ============================================================
// 三入口互斥 / 输入质量门 / 三模式解析 / 去练习联动
const QaState = {
    entry: "text",          // image / pdf / text
    content: "",
    answerKey: "",
    userAnswer: "",
    result: null,           // 最近一次解析结果
    detailShown: false,     // 是否已展开详细讲解
    pendingVisible: false,  // 待确认池面板是否展开
};

const QA_TYPE_LABELS = {
    single_question: "单题",
    passage_with_blanks: "完形填空",
    passage_only: "阅读文章",
    not_japanese: "非日语",
};
const QA_TAG_TYPE_LABELS = {
    grammar: "语法",
    vocab_pair: "易混词",
    comprehension: "理解",
};
const QA_MODE_HINTS = {
    A: "将走：模式 A · 标准答案确定性判分（对错由代码对比，AI 不判分）",
    B: "将走：模式 B · AI 评判你的答案",
    C: "将走：模式 C · AI 解题（低置信，结果带 🤖 标注）",
};

function qaHasJapanese(text) {
    return /[぀-ヿ]/.test(text || "") || /[々・]/.test(text || "");
}
function qaIsPureSymbols(content) {
    const s = content.replace(/\s/g, "");
    if (!s) return false; // 空输入由空检查拦截
    // 不含任何文字/数字/假名/汉字 → 纯符号
    return !/[぀-ヿ㐀-䶿一-鿿０-９Ａ-Ｚａ-ｚa-zA-Z0-9]/.test(s);
}
function qaIsPureNumbers(content) {
    const s = content.replace(/\s/g, "");
    if (!s) return false;
    return s.replace(/[\d０-９]/g, "").trim() === "";
}
function qaValidate(content) {
    // QA-2：输入质量门（零 token，不发起请求）
    if (!content) return { ok: false, msg: "请先粘贴题目内容" };
    if (qaIsPureSymbols(content)) return { ok: false, msg: "输入内容只包含符号，无法识别为题目" };
    if (qaIsPureNumbers(content)) return { ok: false, msg: "输入内容只包含数字，无法识别为题目" };
    if (!qaHasJapanese(content)) return { ok: false, msg: "未检测到日语内容（日文一般含假名）。请确认这是日语题目" };
    return { ok: true };
}
function qaDetectMode(answerKey, userAnswer) {
    if (answerKey && answerKey.trim()) return "A";
    if (userAnswer && userAnswer.trim()) return "B";
    return "C";
}

function showQaScreen() {
    showScreen("qa");
    setDockActive("qa");

    const heroIcon = $("#screen-qa .setup-icon-wrap");
    if (heroIcon) heroIcon.innerHTML = '<i data-lucide="messages-square" style="width:40px;height:40px"></i>';
    const heroTitle = $("#screen-qa .setup-hero h1");
    if (heroTitle) heroTitle.textContent = "答疑";
    const heroDesc = $("#screen-qa .setup-desc");
    if (heroDesc) heroDesc.textContent = "粘贴 / 上传日语题目，AI 帮你解析讲解、判分纠错";

    const card = $("#qa-card");
    if (!card) return;
    card.innerHTML = `
        <div class="qa-entry-grid" id="qa-entry-grid">
            <div class="qa-entry-card" data-entry="image">
                <div class="qa-entry-icon"><i data-lucide="camera" style="width:22px;height:22px"></i></div>
                <span class="qa-entry-name">图片</span>
                <small class="qa-entry-desc">拍照 / 截图</small>
            </div>
            <div class="qa-entry-card" data-entry="pdf">
                <div class="qa-entry-icon"><i data-lucide="file-text" style="width:22px;height:22px"></i></div>
                <span class="qa-entry-name">PDF</span>
                <small class="qa-entry-desc">上传文档</small>
            </div>
            <div class="qa-entry-card active" data-entry="text">
                <div class="qa-entry-icon"><i data-lucide="pencil" style="width:22px;height:22px"></i></div>
                <span class="qa-entry-name">文字</span>
                <small class="qa-entry-desc">粘贴题目</small>
            </div>
        </div>

        <div id="qa-text-area">
            <label class="input-label" for="qa-content-input">题目内容</label>
            <textarea id="qa-content-input" class="input textarea qa-content-input" placeholder="粘贴日语题目。例如：&#10;次の言葉を使って、正しい文を作りなさい。&#10;毎日＿＿＿散歩します。（てから / ながら）"></textarea>
            <p class="input-hint" id="qa-char-count">0 字</p>
        </div>

        <div id="qa-file-upload" style="display:none;">
            <label class="input-label" id="qa-file-label">上传文件</label>
            <div class="qa-drop-zone" id="qa-drop-zone">
                <i data-lucide="upload" style="width:28px;height:28px"></i>
                <p id="qa-drop-text">拖拽文件到这里，或点击选择</p>
                <span class="qa-drop-hint" id="qa-drop-hint">支持 PDF / PNG / JPG / WebP，最大 10 MB</span>
                <input type="file" id="qa-file-input" accept=".pdf,image/png,image/jpg,image/jpeg,image/webp" hidden>
            </div>
            <p class="input-hint" id="qa-file-status"></p>
        </div>

        <div class="qa-optional-grid">
            <div class="qa-optional-field">
                <label class="input-label" for="qa-answer-key">标准答案 <span class="qa-optional-tag">可选</span></label>
                <input type="text" id="qa-answer-key" class="input" placeholder="题目自带答案？填这里可自动判分" autocomplete="off">
            </div>
            <div class="qa-optional-field">
                <label class="input-label" for="qa-user-answer">我的答案 <span class="qa-optional-tag">可选</span></label>
                <input type="text" id="qa-user-answer" class="input" placeholder="你写的答案？AI 评判对错" autocomplete="off">
            </div>
        </div>

        <p class="input-hint" id="qa-mode-hint"></p>

        <div class="qa-actions">
            <button class="btn btn-primary btn-full" id="btn-qa-parse"><i data-lucide="sparkles" style="width:16px;height:16px"></i> 开始解析</button>
        </div>
        <p id="qa-error" class="error-text" style="display:none;"></p>

        <div id="qa-result" class="qa-result" style="display:none;"></div>
    `;
    refreshIcons();

    // 恢复状态（DOM 刚重建，重置文件绑定标记让 PDF 入口重新挂事件）
    resetQaFileBind();
    qaSetEntry(QaState.entry);
    $("#qa-content-input").value = QaState.content;
    $("#qa-answer-key").value = QaState.answerKey;
    $("#qa-user-answer").value = QaState.userAnswer;
    updateQaCharCount();
    updateQaModeHint();

    // 三入口互斥（QA-1：选一个，其余置灰）
    $$("#qa-entry-grid .qa-entry-card").forEach(el => {
        el.onclick = () => qaSetEntry(el.dataset.entry);
    });

    // 输入事件
    $("#qa-content-input").oninput = () => {
        QaState.content = $("#qa-content-input").value;
        updateQaCharCount();
    };
    $("#qa-answer-key").oninput = () => { QaState.answerKey = $("#qa-answer-key").value; updateQaModeHint(); };
    $("#qa-user-answer").oninput = () => { QaState.userAnswer = $("#qa-user-answer").value; updateQaModeHint(); };

    $("#btn-qa-parse").onclick = () => submitQaParse(false);

    // 返回按钮
    const backBtn = $("#btn-qa-back");
    if (backBtn) { backBtn.style.display = ""; backBtn.onclick = showMainScreen; }

    // 若已有结果，重新渲染
    if (QaState.result) renderQaResult(QaState.result);
}

function qaSetEntry(type) {
    QaState.entry = type;
    $$("#qa-entry-grid .qa-entry-card").forEach(el => {
        el.classList.toggle("active", el.dataset.entry === type);
    });
    const textArea = $("#qa-text-area");
    const fileUpload = $("#qa-file-upload");
    const parseBtn = $("#btn-qa-parse");

    if (type === "text") {
        // 文字入口：显示 textarea，隐藏文件上传
        if (textArea) textArea.style.display = "";
        if (fileUpload) fileUpload.style.display = "none";
        if (parseBtn) parseBtn.disabled = false;
    } else {
        // 图片 / PDF 入口：显示文件上传区，隐藏 textarea（提取后在 textarea 回显）
        if (textArea) textArea.style.display = "none";
        if (fileUpload) fileUpload.style.display = "";
        if (parseBtn) parseBtn.disabled = !(QaState.content && QaState.content.trim());
        // 按入口类型更新拖拽区文案，并绑定文件选择事件
        updateQaDropHint(type);
        bindQaFileUpload();
    }
}

function updateQaDropHint(type) {
    const label = $("#qa-file-label");
    const dropText = $("#qa-drop-text");
    const hint = $("#qa-drop-hint");
    if (type === "pdf") {
        if (label) label.textContent = "上传 PDF";
        if (dropText) dropText.textContent = "拖拽 PDF 文件到这里，或点击选择";
        if (hint) hint.textContent = "支持 .pdf，最大 10 MB，最多 50 页";
    } else {
        if (label) label.textContent = "上传图片";
        if (dropText) dropText.textContent = "拖拽截图 / 照片到这里，或点击选择";
        if (hint) hint.textContent = "支持 PNG / JPG / WebP，最大 10 MB";
    }
}

let _qaFileBound = false;
function bindQaFileUpload() {
    if (_qaFileBound) return;
    _qaFileBound = true;

    const dropZone = $("#qa-drop-zone");
    const fileInput = $("#qa-file-input");
    const statusEl = $("#qa-file-status");

    if (!dropZone || !fileInput) { _qaFileBound = false; return; }

    // 点击打开文件选择器
    dropZone.onclick = () => fileInput.click();

    // 拖拽事件
    ["dragenter", "dragover"].forEach(ev => {
        dropZone.addEventListener(ev, e => { e.preventDefault(); dropZone.classList.add("qa-drop-active"); });
    });
    ["dragleave", "drop"].forEach(ev => {
        dropZone.addEventListener(ev, e => { e.preventDefault(); dropZone.classList.remove("qa-drop-active"); });
    });
    dropZone.addEventListener("drop", e => {
        const files = e.dataTransfer.files;
        if (files.length) handleQaFile(files[0], statusEl);
    });

    fileInput.onchange = () => {
        if (fileInput.files.length) handleQaFile(fileInput.files[0], statusEl);
    };
}

function resetQaFileBind() { _qaFileBound = false; }

function qaFileKind(file) {
    const n = (file && file.name || "").toLowerCase();
    if (/\.pdf$/.test(n)) return "pdf";
    if (/\.(png|jpe?g|webp)$/.test(n)) return "image";
    return "";
}

async function handleQaFile(file, statusEl) {
    const kind = qaFileKind(file);
    if (!kind) {
        if (statusEl) statusEl.textContent = "请选择 PDF 或图片（PNG / JPG / WebP）";
        return;
    }
    if (file.size > 10 * 1024 * 1024) {
        if (statusEl) statusEl.textContent = "文件过大（最大 10 MB）";
        return;
    }

    const action = kind === "pdf" ? "提取 PDF 文字" : "识别图片文字";
    if (statusEl) statusEl.textContent = `正在${action}（${(file.size / 1024 / 1024).toFixed(1)} MB）…`;

    const form = new FormData();
    form.append("file", file);

    try {
        const resp = await fetch("/api/qa/upload", { method: "POST", body: form });
        const data = await resp.json();

        if (!data.success) {
            if (statusEl) statusEl.textContent = data.warning || data.error || "提取失败";
            return;
        }

        if (statusEl) statusEl.textContent = kind === "pdf"
            ? `✅ 已提取 ${data.pages} 页，${data.text.length} 字`
            : `✅ 已识别图片文字（${data.text.length} 字）`;
        QaState.content = data.text;

        // 回填 textarea，切换到文字入口让用户编辑
        const textArea = $("#qa-content-input");
        if (textArea) textArea.value = data.text;
        updateQaCharCount();

        // 显示 textarea，隐藏文件上传区
        const ta = $("#qa-text-area");
        const fu = $("#qa-file-upload");
        if (ta) ta.style.display = "";
        if (fu) fu.style.display = "none";

        const parseBtn = $("#btn-qa-parse");
        if (parseBtn) parseBtn.disabled = false;
    } catch (err) {
        if (statusEl) statusEl.textContent = `上传失败：${err.message}`;
    }
}

function updateQaCharCount() {
    const el = $("#qa-char-count");
    if (el) el.textContent = `${($("#qa-content-input").value || "").length} 字`;
}

function updateQaModeHint() {
    const hint = $("#qa-mode-hint");
    if (!hint) return;
    const mode = qaDetectMode(QaState.answerKey, QaState.userAnswer);
    hint.textContent = QA_MODE_HINTS[mode];
}

async function submitQaParse(detail) {
    const content = ($("#qa-content-input").value || "").trim();
    const gate = qaValidate(content);
    if (!gate.ok) {
        showError("qa-error", gate.msg);
        return;
    }
    hide($("#qa-error"));

    const answerKey = ($("#qa-answer-key").value || "").trim();
    const userAnswer = ($("#qa-user-answer").value || "").trim();
    QaState.content = content;
    QaState.answerKey = answerKey;
    QaState.userAnswer = userAnswer;

    showLoading(detail ? "正在生成详细讲解..." : "正在解析题目...");
    try {
        const result = await api("/api/qa/parse", {
            method: "POST",
            body: JSON.stringify({
                content,
                answer_key: answerKey,
                user_answer: userAnswer,
                level: AppState.config.level || "N4",
                detail: !!detail,
            }),
        });
        hideLoading();
        QaState.result = result;
        QaState.detailShown = !!detail;
        renderQaResult(result);
    } catch (err) {
        hideLoading();
        showError("qa-error", err.message);
    }
}

function qaFocusTagsOf(result) {
    return [...new Set((result.knowledge_tags || [])
        .filter(t => t.type === "grammar" || t.type === "vocab_pair")
        .map(t => (t.tag || "").trim())
        .filter(Boolean))];
}

function renderQaResult(result) {
    const wrap = $("#qa-result");
    if (!wrap) return;
    wrap.style.display = "";

    const mode = result.mode || "C";
    const qtype = result.question_type || "";
    const struct = result.structure || {};
    const ans = result.answer || {};

    const modeBadge = {
        A: { cls: "qa-mode-a", text: "模式 A · 确定性判分" },
        B: { cls: "qa-mode-b", text: "模式 B · AI 评判" },
        C: { cls: "qa-mode-c", text: "模式 C · AI 解题 🤖" },
    }[mode] || { cls: "qa-mode-c", text: "模式 " + mode };

    // 题目结构
    let structHtml = "";
    if (struct.stem) structHtml += `<div class="qa-stem">${escapeHtml(struct.stem)}</div>`;
    if (struct.options && struct.options.length) {
        structHtml += `<div class="qa-options">${struct.options.map((o, i) =>
            `<div class="qa-option"><span class="qa-option-letter">${String.fromCharCode(65 + i)}</span>${escapeHtml(o)}</div>`
        ).join("")}</div>`;
    }
    if (struct.passage) {
        structHtml += `<details class="qa-passage"><summary>阅读全文（${struct.passage.length} 字）</summary><p class="qa-passage-body">${escapeHtml(struct.passage)}</p></details>`;
    }
    if (struct.sub_questions && struct.sub_questions.length) {
        structHtml += `<div class="qa-sub-questions">${struct.sub_questions.map(sq => {
            const opts = (sq.options && sq.options.length)
                ? `<div class="qa-options">${sq.options.map((o, i) => `<div class="qa-option"><span class="qa-option-letter">${String.fromCharCode(65 + i)}</span>${escapeHtml(o)}</div>`).join("")}</div>` : "";
            const a = sq.answer ? `<div class="qa-sub-answer">答案：${escapeHtml(sq.answer)}</div>` : "";
            return `<div class="qa-sub-question"><span class="qa-sub-num">${sq.id || ""}</span><div class="qa-sub-body">${escapeHtml(sq.stem)}${opts}${a}</div></div>`;
        }).join("")}</div>`;
    }

    // 答案块
    let ansHtml = "";
    if (mode === "A") {
        let verdictHtml = "";
        if (ans.is_correct === true) verdictHtml = `<div class="qa-verdict qa-verdict-correct">✓ 回答正确</div>`;
        else if (ans.is_correct === false) verdictHtml = `<div class="qa-verdict qa-verdict-wrong">✗ 回答错误</div>`;
        else verdictHtml = `<div class="qa-verdict qa-verdict-neutral">未填「我的答案」，未判分</div>`;
        ansHtml = `
            <div class="qa-answer-block">
                ${verdictHtml}
                <div class="qa-compare-row">
                    <div><small>标准答案</small><p>${escapeHtml(ans.answer_key || "—")}</p></div>
                    <div><small>你的答案</small><p>${escapeHtml(ans.user_answer || "—")}</p></div>
                </div>
            </div>`;
    } else if (mode === "B") {
        ansHtml = `
            <div class="qa-answer-block">
                <div class="qa-compare-row">
                    <div><small>你的答案</small><p>${escapeHtml(ans.user_answer || "—")}</p></div>
                    <div><small>参考解析</small><p>${escapeHtml(ans.correct_answer || "—")}</p></div>
                </div>
                <div class="qa-judgment"><strong>AI 评判：</strong><span>${escapeHtml(ans.judgment || "—")}</span></div>
            </div>`;
    } else {
        const conf = typeof ans.ai_confidence === "number" ? Math.round(ans.ai_confidence * 100) : null;
        ansHtml = `
            <div class="qa-answer-block qa-ai-block">
                <div class="qa-ai-tag">🤖 AI 解答</div>
                <div class="qa-ai-answer">${escapeHtml(ans.correct_answer || "—")}</div>
                ${conf !== null ? `<div class="qa-ai-confidence">置信度 ${conf}%</div>` : ""}
            </div>`;
    }

    // 讲解（QP-7：默认精简，展开调详细版）
    const detailBtnHtml = QaState.detailShown
        ? ""
        : `<button class="btn btn-secondary btn-sm qa-detail-toggle" id="btn-qa-detail"><i data-lucide="chevron-down" style="width:14px;height:14px"></i> 展开详细讲解</button>`;

    // 知识点标签
    const tags = result.knowledge_tags || [];
    const tagsHtml = tags.length ? `<div class="qa-tags">${tags.map(t => {
        const type = (t.type && QA_TAG_TYPE_LABELS[t.type]) ? t.type : "comprehension";
        const inferred = t.ai_inferred ? " 🤖" : "";
        return `<span class="qa-tag-chip qa-tag-${type}">${escapeHtml(QA_TAG_TYPE_LABELS[type])} · ${escapeHtml(t.tag)}${inferred}</span>`;
    }).join("")}</div>` : "";

    // 去练习（QG-1：提取 grammar + vocab_pair）
    const focusTags = qaFocusTagsOf(result);
    const practiceDisabled = focusTags.length === 0;

    // M3：模式 C 且有知识点 → 已入待确认池，提供查看入口
    let pendingNoteHtml = "";
    if (mode === "C" && (result.knowledge_tags || []).length) {
        pendingNoteHtml = `
            <div class="qa-pending-note">
                <i data-lucide="inbox" style="width:14px;height:14px"></i>
                <span>AI 推断知识点已加入「待确认池」</span>
                <button class="btn btn-secondary btn-sm" id="btn-qa-pending-open">查看待确认</button>
            </div>`;
    }

    wrap.innerHTML = `
        <div class="qa-result-divider"></div>
        <div class="qa-result-header">
            <span class="qa-mode-badge ${modeBadge.cls}">${modeBadge.text}</span>
            <span class="qa-type-badge">${escapeHtml(QA_TYPE_LABELS[qtype] || qtype)}</span>
            ${result.cached ? `<span class="qa-cached-badge"><i data-lucide="zap" style="width:12px;height:12px"></i> 缓存</span>` : ""}
        </div>

        <div class="qa-question-block">
            <div class="qa-section-title">📝 题目</div>
            ${structHtml || `<p class="qa-empty">（未提取到题目结构）</p>`}
        </div>

        ${ansHtml}

        <div class="qa-explanation">
            <div class="qa-section-title">💡 讲解</div>
            <div class="qa-explanation-body">${renderMarkdown(result.explanation)}</div>
            ${result.explanation_detail ? `<div class="qa-explanation-detail">${renderMarkdown(result.explanation_detail)}</div>` : ""}
            ${detailBtnHtml}
        </div>

        ${tagsHtml}

        ${pendingNoteHtml}

        <div class="qa-action-row">
            <button class="btn btn-secondary" id="btn-qa-again"><i data-lucide="rotate-ccw" style="width:16px;height:16px"></i> 再解析一道</button>
            <button class="btn btn-primary" id="btn-qa-practice" ${practiceDisabled ? "disabled" : ""}><i data-lucide="arrow-right" style="width:16px;height:16px"></i> 去练习</button>
        </div>
        ${practiceDisabled ? `<p class="input-hint">该题暂无语法 / 易混词知识点，暂不能联动练习</p>` : ""}
    `;
    refreshIcons();

    const detailBtn = $("#btn-qa-detail");
    if (detailBtn) detailBtn.onclick = () => submitQaParse(true);

    const againBtn = $("#btn-qa-again");
    if (againBtn) againBtn.onclick = resetQaForm;

    const practiceBtn = $("#btn-qa-practice");
    if (practiceBtn) practiceBtn.onclick = () => startQaPractice(focusTags);

    const pendingOpenBtn = $("#btn-qa-pending-open");
    if (pendingOpenBtn) pendingOpenBtn.onclick = toggleQaPendingPanel;

    wrap.scrollIntoView({ behavior: "smooth", block: "start" });
}

function resetQaForm() {
    QaState.content = "";
    QaState.answerKey = "";
    QaState.userAnswer = "";
    QaState.result = null;
    QaState.detailShown = false;
    const contentInput = $("#qa-content-input");
    if (contentInput) contentInput.value = "";
    const ak = $("#qa-answer-key"); if (ak) ak.value = "";
    const ua = $("#qa-user-answer"); if (ua) ua.value = "";
    updateQaCharCount();
    updateQaModeHint();
    const err = $("#qa-error"); if (err) hide(err);
    const res = $("#qa-result"); if (res) { res.style.display = "none"; res.innerHTML = ""; }
    if (contentInput) contentInput.focus();
}

async function startQaPractice(focusTags) {
    const tags = focusTags || qaFocusTagsOf(QaState.result);
    if (!tags.length) return;

    const stem = (QaState.result && QaState.result.structure && QaState.result.structure.stem) || "";
    const notes = "专注练习以下知识点：" + tags.join("、") + (stem ? "\n（原题：" + stem + "）" : "");

    showLoading("正在按知识点生成练习题...");
    try {
        const result = await api("/api/generate_questions", {
            method: "POST",
            body: JSON.stringify({
                notes,
                level: AppState.config.level,
                vocabulary: "",
                textbook_vocab: currentBookVocab || [],
                focus_tags: tags,   // M4 起由出题 API 正式消费
            }),
        });
        if (!result.success || !result.data) throw new Error("出题失败，请重试");
        const questions = result.data.questions || [];
        if (!questions.length) throw new Error("未能生成题目，请重试");

        AppState.notes = notes;
        AppState.vocabulary = "";
        AppState.questions = questions;
        AppState.vocabUsed = result.data.vocab_used || [];
        AppState.currentIndex = 0;
        AppState.records = [];
        AppState.totalAnswered = 0;
        AppState.baseTotal = questions.length;

        await saveProgress();
        hideLoading();
        initQuizScreen();
    } catch (err) {
        hideLoading();
        alert(`去练习失败：${err.message}`);
    }
}

// ============================================================
// 答疑（QA）M3 — 待确认池（KB-3/KB-4）
// ============================================================
async function toggleQaPendingPanel() {
    const panel = $("#qa-pending-panel");
    if (!panel) return;
    QaState.pendingVisible = !QaState.pendingVisible;
    panel.style.display = QaState.pendingVisible ? "" : "none";
    if (QaState.pendingVisible) {
        await renderQaPendingList();
        if (panel.scrollIntoView) panel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
}

function qaPendingStatus(msg, isError) {
    const el = $("#qa-pending-status");
    if (!el) return;
    el.textContent = msg;
    el.className = "qa-pending-status" + (isError ? " error-text" : "");
    show(el);
}

async function renderQaPendingList() {
    const panel = $("#qa-pending-panel");
    if (!panel) return;
    panel.innerHTML = `
        <div class="qa-pending-header">
            <h3><i data-lucide="inbox" style="width:18px;height:18px"></i> 待确认池</h3>
            <button class="btn btn-text btn-sm" id="btn-qa-pending-close">收起</button>
        </div>
        <p class="input-hint">模式 C（纯题目）解析出的 AI 推断知识点在此待确认，确认后才进入 SM-2 复习。</p>
        <div id="qa-pending-body"><p class="input-hint">加载中...</p></div>
        <p class="qa-pending-status" id="qa-pending-status" style="display:none;"></p>
    `;
    refreshIcons();
    $("#btn-qa-pending-close").onclick = () => {
        QaState.pendingVisible = false;
        panel.style.display = "none";
    };
    try {
        const res = await api("/api/qa/pending");
        renderQaPendingBody(res.items || []);
    } catch (err) {
        qaPendingStatus(err.message, true);
    }
}

function renderQaPendingBody(items) {
    const body = $("#qa-pending-body");
    if (!body) return;
    if (!items.length) {
        body.innerHTML = `<p class="input-hint">待确认池是空的。</p>`;
        return;
    }
    body.innerHTML = items.map(item => {
        const tags = (item.knowledge_tags || []).map(t =>
            `<span class="qa-tag-chip qa-tag-${t.type || "comprehension"}">${escapeHtml(t.tag)}</span>`
        ).join(" ");
        const conf = typeof item.ai_confidence === "number"
            ? ` · 置信度 ${Math.round(item.ai_confidence * 100)}%` : "";
        return `
            <div class="qa-pending-item" data-id="${escapeHtml(item.id)}">
                <div class="qa-pending-item-head">
                    <span class="qa-pending-item-time">${escapeHtml((item.parsed_at || "").slice(0, 16))}</span>
                    <span class="qa-pending-item-mode">AI 推断${conf}</span>
                </div>
                <p class="qa-pending-item-preview">${escapeHtml(item.content_preview || "")}</p>
                <div class="qa-pending-item-tags">${tags}</div>
                ${item.ai_answer ? `<p class="qa-pending-item-answer">🤖 ${escapeHtml(item.ai_answer)}</p>` : ""}
                <div class="qa-pending-item-actions">
                    <button class="btn btn-primary btn-sm qa-pending-confirm">确认入库</button>
                    <button class="btn btn-secondary btn-sm qa-pending-reparse">补答案键重解析</button>
                    <button class="btn btn-text btn-sm qa-pending-discard">丢弃</button>
                </div>
                <div class="qa-reparse-box" style="display:none;">
                    <input type="text" class="input" placeholder="粘贴这道题的标准答案，重新解析后覆盖 AI 推断" autocomplete="off">
                    <button class="btn btn-primary btn-sm qa-reparse-submit">重新解析</button>
                </div>
            </div>`;
    }).join("");
    refreshIcons();

    body.querySelectorAll(".qa-pending-confirm").forEach(btn => {
        btn.onclick = () => confirmQaPending(btn.closest(".qa-pending-item").dataset.id);
    });
    body.querySelectorAll(".qa-pending-discard").forEach(btn => {
        btn.onclick = () => discardQaPending(btn.closest(".qa-pending-item").dataset.id);
    });
    body.querySelectorAll(".qa-pending-reparse").forEach(btn => {
        btn.onclick = () => {
            const box = btn.closest(".qa-pending-item").querySelector(".qa-reparse-box");
            box.style.display = box.style.display === "none" ? "" : "none";
        };
    });
    body.querySelectorAll(".qa-reparse-submit").forEach(btn => {
        btn.onclick = async () => {
            const item = btn.closest(".qa-pending-item");
            const answerKey = item.querySelector(".qa-reparse-box input").value.trim();
            await reparseQaPending(item.dataset.id, answerKey);
        };
    });
}

async function confirmQaPending(id) {
    showLoading("正在确认入库...");
    try {
        const res = await api("/api/qa/pending/confirm", {
            method: "POST",
            body: JSON.stringify({ ids: [id] }),
        });
        hideLoading();
        let msg = `已确认 ${res.confirmed} 条知识点入库`;
        if (res.fuzzy && res.fuzzy.length) {
            msg += `；${res.fuzzy.length} 条存在相近知识点，需进一步核对`;
        }
        qaPendingStatus(msg);
        renderQaPendingList();
    } catch (err) {
        hideLoading();
        qaPendingStatus(err.message, true);
    }
}

async function discardQaPending(id) {
    showLoading("正在丢弃...");
    try {
        const res = await api("/api/qa/pending/discard", {
            method: "POST",
            body: JSON.stringify({ ids: [id] }),
        });
        hideLoading();
        qaPendingStatus(`已丢弃 ${res.discarded} 条`);
        renderQaPendingList();
    } catch (err) {
        hideLoading();
        qaPendingStatus(err.message, true);
    }
}

async function reparseQaPending(id, answerKey) {
    if (!answerKey) { qaPendingStatus("请先填写这道题的标准答案", true); return; }
    showLoading("正在重新解析...");
    try {
        const res = await api("/api/qa/pending/reparse", {
            method: "POST",
            body: JSON.stringify({ id, answer_key: answerKey, level: AppState.config.level || "N4" }),
        });
        hideLoading();
        QaState.result = res.result;
        QaState.detailShown = false;
        qaPendingStatus("已按标准答案重新解析，请再次「确认入库」");
        renderQaPendingList();
        if (QaState.result) renderQaResult(QaState.result);
    } catch (err) {
        hideLoading();
        qaPendingStatus(err.message, true);
    }
}

// ============================================================
// 主题管理
// ============================================================
function getTheme() { return localStorage.getItem('kotoba-theme') || 'auto'; }
function setTheme(theme) { localStorage.setItem('kotoba-theme', theme); applyTheme(); }
function applyTheme() {
    const theme = getTheme();
    document.documentElement.removeAttribute('data-theme');
    if (theme === 'dark') document.documentElement.setAttribute('data-theme', 'dark');
    if (theme === 'light') document.documentElement.setAttribute('data-theme', 'light');
}
applyTheme(); // 页面加载时立即应用

// 页面加载完成后启动
document.addEventListener("DOMContentLoaded", () => {
    if (typeof lucide !== "undefined") lucide.createIcons();
    init();
    // Dock 导航
    if (typeof initDock === 'function') initDock();
    // 延迟确保 DOM 就绪
    setTimeout(() => {
        // BorderGlow — 给带 data-glow 的卡片加边缘发光
        if (typeof initBorderGlowCards === 'function') {
            initBorderGlowCards();
        }
    }, 600);

    // 关闭页面时自动退出 Flask（区分页面内跳转 vs 真正关闭）
    let _navTimestamp = 0;
    const _origShowScreen = showScreen;
    showScreen = function(name) {
        _navTimestamp = Date.now();
        return _origShowScreen(name);
    };
    window.addEventListener("beforeunload", () => {
        // 500ms 内有页面跳转 → 是应用内导航，不杀进程
        if (Date.now() - _navTimestamp < 500) return;
        navigator.sendBeacon("/api/shutdown");
    });
});
