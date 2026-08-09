@echo off
chcp 65001 >nul
echo ==========================================
echo   KOTOBA·AI — 打包构建脚本
echo ==========================================
echo.

REM 清理旧构建文件
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist __pycache__ rmdir /s /q __pycache__

echo [1/2] 正在打包...
pyinstaller --noconsole --onefile --name "KOTOBA-AI" ^
    --icon "logo.ico" ^
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
    app.py

if %errorlevel% neq 0 (
    echo 打包失败！
    pause
    exit /b %errorlevel%
)

echo.
echo [2/2] 清理临时文件...
rmdir /s /q build
del /q KOTOBA-AI.spec 2>nul

echo.
echo ==========================================
echo   打包完成！
echo   文件位置：dist\KOTOBA-AI.exe
echo ==========================================
echo.
pause
