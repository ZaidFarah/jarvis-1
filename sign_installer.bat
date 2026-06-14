@echo off
setlocal

set "ROOT=%~dp0"
pushd "%ROOT%" || exit /b 1

if /I not "%SIGNING_ENABLED%"=="true" (
    echo Signing is disabled. Set SIGNING_ENABLED=true to sign the installer later.
    popd
    exit /b 0
)

for /f "delims=" %%F in ('dir /b /a:-d "installer\output\*.exe" 2^>nul') do set "INSTALLER_EXE=installer\output\%%F"

if not defined INSTALLER_EXE (
    echo No installer EXE found in installer\output.
    popd
    exit /b 1
)

if not defined SIGNING_CERT_PATH (
    echo SIGNING_CERT_PATH is not configured.
    popd
    exit /b 1
)

if not defined SIGNING_TIMESTAMP_URL (
    echo SIGNING_TIMESTAMP_URL is not configured.
    popd
    exit /b 1
)

where signtool.exe >nul 2>nul
if errorlevel 1 (
    echo signtool.exe was not found.
    popd
    exit /b 1
)

signtool sign /fd SHA256 /tr "%SIGNING_TIMESTAMP_URL%" /td SHA256 /d "%SIGNING_DESCRIPTION%" /f "%SIGNING_CERT_PATH%" "%INSTALLER_EXE%"
set "EXIT_CODE=%ERRORLEVEL%"

popd
exit /b %EXIT_CODE%
