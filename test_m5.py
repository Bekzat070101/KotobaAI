"""M5 成本完善测试：文件上传（PDF 提取 / 图片 OCR）+ 文件边界 + 关键回归。

运行：python test_m5.py

- stub LLM：分类/解析 prompt 按内容分支返回固定 JSON（零联网）
- stub OCR：monkeypatch app.ocr_process 避免真实模型拖慢；另含一条真实 OCR 集成用例
- 隔离：qa 缓存重定向到临时目录，知识库上下文 / 待确认池写入打桩
"""

import io
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as appmod
import qa_pipeline
import PyPDF2

# --- 隔离：缓存重定向到临时目录，避免污染真实 cache/qa_cache.json ---
TMP = tempfile.mkdtemp(prefix="koto_m5_")
qa_pipeline.CACHE_FILE = os.path.join(TMP, "qa_cache.json")


_KANA_RE = re.compile(r"[぀-ヿ]")


def _stub_llm(prompt, require_json=True):
    """按 prompt 内容分支：分类 prompt → 分类 JSON；解析 prompt → 解析 JSON。"""
    if "分类器" in prompt:
        # 分类 prompt 内嵌题目内容：无假名（纯中文/其他语言）→ not_japanese
        if not _KANA_RE.search(prompt):
            return json.dumps({"question_type": "not_japanese", "reason": "stub"}, ensure_ascii=False)
        return json.dumps({"question_type": "single_question", "reason": "stub"}, ensure_ascii=False)
    return json.dumps({
        "structure": {"stem": "テスト問題です。", "options": [], "passage": None, "sub_questions": []},
        "answer": {"value": "答え", "confidence": 0.9, "judgment": "正确"},
        "explanation": "stub 讲解。",
        "knowledge_tags": [{"tag": "〜は〜です", "type": "grammar"}],
    }, ensure_ascii=False)


class UploadRouteTest(unittest.TestCase):
    """/api/qa/upload 文件上传与边界。"""

    @classmethod
    def setUpClass(cls):
        cls.client = appmod.app.test_client()
        # OCR 打桩：默认快速返回，个别用例临时覆盖
        appmod.ocr_process = lambda b: "次の文を読んで、質問に答えなさい。\n毎日、私は図書館で日本語を勉強します。"

    def _post(self, filename, data: bytes):
        return self.client.post(
            "/api/qa/upload",
            data={"file": (io.BytesIO(data), filename)},
            content_type="multipart/form-data",
        )

    def test_unsupported_extension(self):
        resp = self._post("notes.txt", b"hello")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("暂不支持", resp.get_json()["error"])

    def test_empty_file(self):
        resp = self._post("empty.png", b"")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("文件为空", resp.get_json()["error"])

    def test_file_too_large(self):
        resp = self._post("big.png", b"\x00" * (10 * 1024 * 1024 + 1))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("文件过大", resp.get_json()["error"])

    def test_body_over_max_content_length(self):
        # 超过全局 MAX_CONTENT_LENGTH（11MB）→ Flask 413
        resp = self._post("huge.pdf", b"\x00" * (12 * 1024 * 1024))
        self.assertEqual(resp.status_code, 413)

    def test_image_upload_stub_ocr(self):
        resp = self._post("shot.png", b"fake-png-bytes")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data["success"])
        self.assertIn("次の文を読んで", data["text"])
        self.assertEqual(data["pages"], 1)
        self.assertEqual(data["ext"], "png")

    def test_image_upload_ocr_no_text(self):
        appmod.ocr_process = lambda b: ""
        try:
            resp = self._post("blank.jpg", b"fake-jpg-bytes")
        finally:
            appmod.ocr_process = lambda b: "次の文を読んで、質問に答えなさい。\n毎日、私は図書館で日本語を勉強します。"
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(data["success"])
        self.assertIn("未能识别到足够文字", data["warning"])

    def test_image_upload_bad_image(self):
        def bad_img(b):
            raise ValueError("无法识别该图片格式，请上传 PNG / JPG / WebP 图片")
        appmod.ocr_process = bad_img
        try:
            resp = self._post("corrupt.png", b"not-an-image")
        finally:
            appmod.ocr_process = lambda b: "次の文を読んで、質問に答えなさい。\n毎日、私は図書館で日本語を勉強します。"
        data = resp.get_json()
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(data["success"])
        self.assertIn("无法识别", data["warning"])

    def test_pdf_blank_scan_warning(self):
        # 空白页 PDF：无文本 → 扫描件 warning（指向图片入口）
        writer = PyPDF2.PdfWriter()
        writer.add_blank_page(width=612, height=792)
        buf = io.BytesIO()
        writer.write(buf)
        resp = self._post("scan.pdf", buf.getvalue())
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(data["success"])
        self.assertIn("图片", data["warning"])


class OcrIntegrationTest(unittest.TestCase):
    """真实 OCR 管线（日文模型）端到端验证。"""

    def test_real_ocr_japanese(self):
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (900, 120), "white")
        d = ImageDraw.Draw(img)
        font = ImageFont.truetype(r"C:\Windows\Fonts\YuGothR.ttc", 34)
        d.text((30, 40), "電車の中で本を読んでいる人は誰ですか。", fill="black", font=font)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        text = appmod.ocr_process(buf.getvalue())
        self.assertIn("電車", text)
        self.assertIn("本を読んで", text)


class ParseRegressionTest(unittest.TestCase):
    """关键回归：三模式分流 / 确定性判分 / 缓存命中 / 非日语拦截。"""

    @classmethod
    def setUpClass(cls):
        cls.client = appmod.app.test_client()
        appmod.call_deepseek = _stub_llm
        appmod.build_qa_knowledge_context = lambda *a, **k: ""
        appmod.collect_pending = lambda *a, **k: None
        cls.stub_calls = {"n": 0}
        orig = _stub_llm

        def counting(prompt, require_json=True):
            cls.stub_calls["n"] += 1
            return orig(prompt, require_json)
        appmod.call_deepseek = counting

    def _parse(self, payload):
        return self.client.post("/api/qa/parse", json=payload)

    def test_mode_a_deterministic_grade(self):
        resp = self._parse({"content": "次の言葉を使って文を作りなさい。", "answer_key": "私は図書館で勉強します", "user_answer": "私は図書館で勉強します"})
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data["mode"], "A")
        self.assertTrue(data["answer"]["is_correct"])  # 确定性判分
        self.assertFalse(data["ai_answered"])

    def test_mode_c_ai_solved(self):
        resp = self._parse({"content": "これは昨日、友達からもらった本です。"})
        data = resp.get_json()
        self.assertEqual(data["mode"], "C")
        self.assertTrue(data["ai_answered"])
        self.assertTrue(data["knowledge_tags"][0]["ai_inferred"])

    def test_cache_hit_zero_llm(self):
        before = self.stub_calls["n"]
        payload = {"content": "電車で学校へ行きます。"}
        self._parse(payload)
        mid = self.stub_calls["n"]
        resp2 = self._parse(payload)  # 第二次应命中缓存
        after = self.stub_calls["n"]
        self.assertEqual(mid - before, 2)  # 首次：分类 + 解析
        self.assertEqual(after - mid, 0)   # 二次：零 LLM 调用
        self.assertTrue(resp2.get_json()["cached"])

    def test_not_japanese_rejected(self):
        resp = self._parse({"content": "这是一道中文题，请帮我解析。"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("未检测到日语", resp.get_json()["error"])


class ClassifyRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = appmod.app.test_client()
        appmod.call_deepseek = _stub_llm

    def test_classify_single(self):
        resp = self.client.post("/api/qa/classify", json={"content": "これは何ですか。"})
        data = resp.get_json()
        self.assertEqual(data["question_type"], "single_question")
        self.assertEqual(data["mode"], "C")

    def test_classify_empty(self):
        resp = self.client.post("/api/qa/classify", json={"content": ""})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("不能为空", resp.get_json()["error"])


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
