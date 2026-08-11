@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM KOTOBA-AI - run WACK (Windows App Certification Kit) on the built .msix
REM Usage: cmd /c "C:\...\msix\run_wack.bat"
REM
REM NOTE: appcert.exe CLI often crashes (exit -1) with no report - a known WACK bug,
REM especially for non-installed packages. If that happens, use the GUI below instead.
set WACK="C:\Program Files (x86)\Windows Kits\10\App Certification Kit\appcert.exe"
set WACKUI="C:\Program Files (x86)\Windows Kits\10\App Certification Kit\appcertui.exe"
set MSIX=KOTOBA-AI-4.0.1.0-x64.msix
if not exist %WACK% ( echo [ERROR] WACK not found & exit /b 1 )
if not exist "%MSIX%" ( echo [ERROR] %MSIX% not found & exit /b 1 )

echo Testing %MSIX% ... this can take 5-15 minutes.
%WACK% test -apptype package -appx "%~dp0%MSIX%" -reportoutput "%~dp0wack.xml"
if exist "%~dp0wack.xml" (
  echo WACK report written: wack.xml
  echo Open it and check "Fail" count.
) else (
  echo.
  echo [WARN] WACK CLI crashed (exit %errorlevel%%) with no report - known appcert.exe bug.
  echo Use the GUI wizard instead - double-click and run it:
  echo   %WACKUI%
  echo   - Choose "App installed in this computer" OR "Windows app package"
  echo   - Pick %MSIX%, run tests, review the report.
  echo Note: Partner Center also runs WACK-equivalent validation on submission,
  echo       so local WACK is a pre-check, not a hard gate.
)
