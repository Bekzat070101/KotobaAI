@echo off
chcp 65001 >nul
REM 仅重建 onedir（商店 MSIX 消费 dist\KOTOBA-AI\），不动 portable / installer。
REM 代码/前端改动后跑它即可，比根 build.bat 快（跳过 onefile 与 Inno Setup）。
REM 用法（git-bash）：cmd //c "C:\Users\Aa233\Desktop\JapAI\msix\rebuild_onedir.bat"

cd /d "%~dp0\.."

REM 只重建 onedir，绝不能清整个 dist/（那里有便携版/zip/安装包，会被误删！）
if exist build-install rmdir /s /q build-install
if exist dist-install rmdir /s /q dist-install
if exist __pycache__ rmdir /s /q __pycache__
if exist KOTOBA-AI.spec del /q KOTOBA-AI.spec

echo [1/1] building onedir (dist\KOTOBA-AI\)...
pyinstaller --noconsole --icon "logo.ico" ^
  --add-data "static;static" ^
  --add-data "knowledge_base;knowledge_base" ^
  --add-data "ocr_models;ocr_models" ^
  --hidden-import "prompts" ^
  --hidden-import "prompts.generate_questions" ^
  --hidden-import "prompts.grade_answer" ^
  --hidden-import "prompts.generate_summary" ^
  --collect-all rapidocr_onnxruntime ^
  --collect-all onnxruntime ^
  --collect-all cv2 ^
  --name "KOTOBA-AI" ^
  --distpath dist-install ^
  --workpath build-install app.py
if errorlevel 1 goto :fail

mkdir dist >nul 2>nul
if exist dist\KOTOBA-AI rmdir /s /q dist\KOTOBA-AI
xcopy /e /i /q /y dist-install\KOTOBA-AI dist\KOTOBA-AI\ >nul
if errorlevel 1 goto :fail

rmdir /s /q build-install
rmdir /s /q dist-install
del /q KOTOBA-AI.spec 2>nul

echo.
echo ========== onedir rebuild DONE: dist\KOTOBA-AI\ ==========
exit /b 0

:fail
echo.
echo ========== onedir rebuild FAILED ==========
exit /b %errorlevel%
