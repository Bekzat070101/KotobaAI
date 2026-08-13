@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

REM ============================================================
REM  KOTOBA-AI - MSIX Store packaging script (PRD M8.3)
REM  Prerequisite: run root build.bat first to produce onedir at
REM    ..\dist\KOTOBA-AI\  (exe + _internal)
REM  Run from git-bash as:
REM    cmd //c "C:\Users\Aa233\Desktop\JapAI\msix\build_msix.bat"
REM  Output: KOTOBA-AI-<version>-x64.msix  +  dev_cert.pfx/.cer
REM ============================================================

REM ---- Editable config -------------------------------------
REM  For STORE submission, NAME/PUBLISHER are the values reserved
REM  in Partner Center (产品管理 → 产品标识). They must match
REM  EXACTLY (one char off => rejected).
SET MSIX_NAME=drRevo.KotobaAI
SET MSIX_PUBLISHER=CN=D6448763-9FA2-446E-BA65-F8A66E3A5AD2
SET MSIX_PUBLISHER_DISPLAY=drRevo
SET MSIX_VERSION=4.0.1.1
SET MSIX_MIN_VERSION=10.0.17763.0
SET MSIX_MAX_VERSION=10.0.26100.0

REM onedir produced by build.bat
SET ONEDIR=..\dist\KOTOBA-AI
REM password for the local self-signed dev cert
SET CERT_PASSWORD=KotobaAI2026

REM installed Windows SDK kit version
SET KIT=10.0.28000.0
SET MAKEAPPX="C:\Program Files (x86)\Windows Kits\10\bin\%KIT%\x64\makeappx.exe"
SET SIGNTOOL="C:\Program Files (x86)\Windows Kits\10\bin\%KIT%\x64\signtool.exe"
SET WACK_GUI="C:\Program Files (x86)\Windows Kits\10\App Certification Kit\appcertui.exe"

SET STAGING=staging
SET OUT=%MSIX_NAME%-%MSIX_VERSION%-x64.msix

REM ---- Preflight checks -------------------------------------
if not exist "%ONEDIR%\KOTOBA-AI.exe" (
  echo [ERROR] onedir not found: %ONEDIR%
  echo   Run build.bat in the project root first, then retry.
  exit /b 1
)
if not exist %MAKEAPPX% (
  echo [ERROR] makeappx.exe not found ^(KIT=%KIT%^).
  echo   Install Windows SDK or update the KIT variable above.
  exit /b 1
)
if not exist %SIGNTOOL% (
  echo [ERROR] signtool.exe not found ^(KIT=%KIT%^).
  exit /b 1
)

REM ---- 1/6 clean staging ------------------------------------
echo [1/6] clean staging...
if exist "%STAGING%" rmdir /s /q "%STAGING%"
mkdir "%STAGING%\Assets" >nul

REM ---- 2/6 generate icon assets -----------------------------
echo [2/6] generating store icons...
python make_assets.py
if errorlevel 1 ( echo [ERROR] make_assets.py failed & exit /b 1 )

REM ---- 3/6 render AppxManifest.xml --------------------------
echo [3/6] rendering AppxManifest.xml...
powershell -NoProfile -ExecutionPolicy Bypass -File render_manifest.ps1 ^
  -Template AppxManifest.xml.tpl ^
  -Out "%STAGING%\AppxManifest.xml" ^
  -Name "%MSIX_NAME%" ^
  -Publisher "%MSIX_PUBLISHER%" ^
  -PublisherDisplay "%MSIX_PUBLISHER_DISPLAY%" ^
  -Version "%MSIX_VERSION%" ^
  -MinVersion "%MSIX_MIN_VERSION%" ^
  -MaxVersion "%MSIX_MAX_VERSION%"
if errorlevel 1 ( echo [ERROR] manifest render failed & exit /b 1 )

REM ---- 4/6 copy onedir flat into package --------------------
echo [4/6] copying onedir into package (this takes a while)...
xcopy "%ONEDIR%\*" "%STAGING%\" /e /i /q /y >nul
if errorlevel 1 ( echo [ERROR] copy failed & exit /b 1 )

REM ---- 5/6 MakeAppx pack ------------------------------------
echo [5/6] packing msix...
%MAKEAPPX% pack /d "%STAGING%" /p "%OUT%" /o
if errorlevel 1 ( echo [ERROR] makeappx pack failed & exit /b 1 )

REM ---- 6/6 sign with self-signed dev cert -------------------
echo [6/6] signing...
powershell -NoProfile -ExecutionPolicy Bypass -File make_dev_cert.ps1 ^
  -Publisher "%MSIX_PUBLISHER%" ^
  -Password "%CERT_PASSWORD%" ^
  -CertDir .
if errorlevel 1 ( echo [ERROR] cert creation failed & exit /b 1 )
%SIGNTOOL% sign /fd SHA256 /f dev_cert.pfx /p %CERT_PASSWORD% "%OUT%"
if errorlevel 1 ( echo [ERROR] signtool sign failed & exit /b 1 )

echo.
echo ========== DONE ==========
for %%A in ("%OUT%") do echo %%~zA bytes  ^(%OUT%^)
echo.

REM ---- Optional: install on THIS PC for real-device test ----
set /p INSTALL="Install on this PC now for real-device test? (y/n): "
if /i not "%INSTALL%"=="y" goto :skip_install

echo Trusting dev cert in LocalMachine stores ^(AppXSvc runs as SYSTEM; user stores do NOT count^)...
echo   NOTE: this step needs an ADMIN prompt - if it fails, close and re-run this bat as Administrator.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Import-Certificate -FilePath 'dev_cert.cer' -CertStoreLocation Cert:\LocalMachine\Root | Out-Null; Import-Certificate -FilePath 'dev_cert.cer' -CertStoreLocation Cert:\LocalMachine\TrustedPeople | Out-Null"
echo Installing %OUT% ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-AppxPackage -Path '%cd%\%OUT%'"
if errorlevel 1 (
  echo [WARN] install failed - see message above.
  echo   If it mentions a signature/trust error, run the TrustedPeople import again as that user.
) else (
  echo Install OK. Search "KOTOBA-AI" in Start menu.
)

:skip_install
echo.
echo WACK test ^(optional, GUI^): %WACK_GUI%
echo   Or in PowerShell: appcert.exe test -apptype package -appx %cd%\%OUT% -reportoutput wack.xml
echo Local reinstall later: Add-AppxPackage -Path %cd%\%OUT%   ^(dev cert already trusted^)
echo For STORE: edit MSIX_NAME/MSIX_PUBLISHER at top of this file, rebuild, then submit
echo   the .msix to Partner Center - Microsoft re-signs it, no SmartScreen warning.
endlocal
