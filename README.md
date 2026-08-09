# KOTOBA·AI — AI 日语语法闯关练习

一款免费开源的 Windows 本地日语学习工具。粘贴语法笔记 → AI 生成场景翻译题 → 逐题闯关批改 → 自动生成复习笔记。

**搭配《标准日本语》等教材使用，随学随练，越用越聪明。**

---

## 下载

从 [GitHub Releases](https://github.com/Bekzat070101/KotobaAI/releases) 下载，两种方式任选：

- **安装版**：`KOTOBA-AI-Setup-*.exe` —— 建议大部分用户使用。按用户安装（无需管理员权限），开始菜单/桌面快捷方式，卸载时可选择是否删除学习数据。
- **便携版**：`KOTOBA-AI-portable.zip` —— 解压即用，无需安装，适合放在 U 盘/移动目录。

**更新**：直接下载新版 `Setup.exe` 运行即可**覆盖升级**，无需卸载重装，学习数据不会丢失（安装器会记住上次的安装路径，自定义路径也能准确替换）。

> 若杀毒软件（360/腾讯管家/火绒等）误报，请在杀软中放行。项目为 GPL-3.0 开源，代码完全可见，可自行用源码验证。

首次使用需准备 [DeepSeek API Key](https://platform.deepseek.com/api_keys)。

---

## 功能

| 功能 | 说明 |
|------|------|
| 📖 场景出题 | 粘贴笔记，AI 提取语法点生成带生活场景的翻译题 |
| 🎯 逐题批改 | ✅/❌/💡 逐项标注，分析对在哪、为什么错、更自然的说法 |
| 🔥 难度递进 | 答得好自动升级 Lv1→Lv2→Lv3，同语法点更深更难 |
| ❓ 答疑模块 | 三种模式（A 带答案键判分 / B 用户作答评判 / C 纯题解题），解析带缓存 |
| 🖼️ 图片识别 | 拍照/截图真题，RapidOCR 日文识别后直接出题 |
| 📄 PDF 识别 | 上传 PDF 讲义自动提取文字 |
| 📦 学习数据导入导出 | 除 API Key 外全量备份，版本更新/换机不丢数据 |
| ✍️ 题型多样化 | 翻译 / 填空 / 混合三种题型，填空确定性判分零 LLM 成本 |
| 📝 错题本 | 按语法点分组整理，支持展开详情和重新练习 |
| 🧠 艾宾浩斯复习 | SM-2 间隔记忆算法，自动追踪掌握度，到期提醒复习 |
| 📅 打卡月历 | 扫描历史记录，统计连续打卡天数 |
| 📋 复习笔记 | 完成一轮自动生成 Markdown 复习报告，可下载 |
| 🌓 深色模式 | 支持浅色/深色/跟随系统 |
| 📚 语法范围 | 内置 N5~N1 全套 508 个 JLPT 语法点，可多选聚焦出题 |

---

## 本地优先

- API Key、学习数据全部存储在本地 JSON 文件
- 除调用 DeepSeek API 外无需联网
- 不上传、不收集、不埋点

## 数据存储

所有用户数据（配置、答题进度、错题本、知识库、历史记录、复习笔记等）默认存放在：

```
%APPDATA%\KOTOBA-AI
```

可在**设置 → 功能设置 → 数据目录**中更改到任意文件夹（更改时自动迁移现有数据并重启生效）。数据与程序安装目录完全分离，升级/卸载程序不会影响学习数据；卸载时也可选择一并删除。
- GPL-3.0 开源，任何使用/修改/分发都必须保留开源，不得闭源商用

---

## 开发

```bash
pip install -r requirements.txt
python app.py
```

### 打包

```bash
build.bat
```

### 项目结构

```
KOTOBA·AI/
├── app.py                  # Flask + pywebview 主程序
├── qa_pipeline.py          # 答疑解析后端（三模式 A/B/C）
├── knowledge_mapper.py     # 知识库映射去重 + TF-IDF 检索
├── test_m5.py              # 自动化测试（test_client + stub LLM）
├── requirements.txt
├── build.bat               # PyInstaller 打包脚本
├── logo.ico                # exe 图标
│
├── prompts/                # AI Prompt 模板（含 qa_parse.py）
├── static/                 # 前端 HTML/CSS/JS + logo 资源
├── knowledge_base/         # JLPT N5~N1 语法库（jlpt_cards/ 508 点）
├── ocr_models/             # 日文 OCR 识别模型（japan_PP-OCRv4）
│
├── config.json             # 用户配置（本地，不入库）
├── learned_content.json    # 已学语法追踪（SM-2，本地）
├── wrong_book.json         # 错题本（本地）
```

---

## License

[GPL-3.0](LICENSE) © [Bekzat070101](https://github.com/Bekzat070101)
