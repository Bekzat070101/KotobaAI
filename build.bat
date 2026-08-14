@echo off
chcp 65001 >nul
echo ==========================================
echo   KOTOBA·AI — 打包构建脚本
echo ==========================================
echo.

REM 清理旧构建文件
if exist build-portable rmdir /s /q build-portable
if exist build-install rmdir /s /q build-install
if exist dist-portable rmdir /s /q dist-portable
if exist dist-install rmdir /s /q dist-install
if exist dist rmdir /s /q dist
if exist __pycache__ rmdir /s /q __pycache__

REM 通用 PyInstaller 参数
set "COMMON=--noconsole --icon "logo.ico" --add-data "static;static" --add-data "knowledge_base;knowledge_base" --add-data "ocr_models;ocr_models" --hidden-import "prompts" --hidden-import "prompts.generate_questions" --hidden-import "prompts.grade_answer" --hidden-import "prompts.generate_summary" --collect-all rapidocr_onnxruntime --collect-all onnxruntime --collect-all cv2 app.py"

echo [1/3] 打包便携版（onefile）...
pyinstaller --onefile --name "KOTOBA-AI" --distpath dist-portable --workpath build-portable %COMMON%
if errorlevel 1 goto :fail

echo.
echo [2/3] 打包安装版（onedir）...
pyinstaller --name "KOTOBA-AI" --distpath dist-install --workpath build-install %COMMON%
if errorlevel 1 goto :fail

echo.
echo [3/3] 组装 dist 并生成安装包...
mkdir dist
copy /y dist-portable\KOTOBA-AI.exe dist\KOTOBA-AI-portable.exe >nul
xcopy /e /i /q /y dist-install\KOTOBA-AI dist\KOTOBA-AI\ >nul
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\KOTOBA-AI-portable.exe' -DestinationPath 'dist\KOTOBA-AI-portable.zip'"

REM Inno Setup 安装包（未安装则跳过，不影响便携版产物）
set "ISCC_EXE="
where iscc >nul 2>nul
if not errorlevel 1 set "ISCC_EXE=iscc"
if errorlevel 1 if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE goto :no_iscc
"%ISCC_EXE%" "installer\setup.iss"
if errorlevel 1 goto :fail
goto :iscc_done
:no_iscc
echo.
echo [提示] 未检测到 Inno Setup ^(iscc^)，跳过安装包生成。
echo        请先安装 Inno Setup 6：https://jrsoftware.org/
echo        便携安装请放入 %%LOCALAPPDATA%%\Programs\Inno Setup 6
:iscc_done

REM 清理临时目录
rmdir /s /q build-portable
rmdir /s /q build-install
rmdir /s /q dist-portable
rmdir /s /q dist-install
del /q KOTOBA-AI.spec 2>nul

echo.
echo ==========================================
echo   打包完成！
echo   便携版：dist\KOTOBA-AI-portable.exe
echo   便携版ZIP：dist\KOTOBA-AI-portable.zip
echo   安装版目录：dist\KOTOBA-AI\
echo   安装包：dist\KOTOBA-AI-Setup-*.exe（若已装 Inno Setup，版本见 setup.iss）
echo ==========================================
echo.
pause
exit /b 0

:fail
echo.
echo 打包失败！
pause
exit /b %errorlevel%
