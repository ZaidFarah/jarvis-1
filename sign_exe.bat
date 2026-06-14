@echo off
setlocal

set "ROOT=%~dp0"
pushd "%ROOT%" || exit /b 1

if /I not "%SIGNING_ENABLED%"=="true" (
    echo Signing is disabled. Set SIGNING_ENABLED=true to sign the EXE later.
    popd
    exit /b 0
)

if not exist "dist\Jarvis\Jarvis.exe" (
    echo Missing dist\Jarvis\Jarvis.exe.
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

signtool sign /fd SHA256 /tr "%SIGNING_TIMESTAMP_URL%" /td SHA256 /d "%SIGNING_DESCRIPTION%" /f "%SIGNING_CERT_PATH%" "dist\Jarvis\Jarvis.exe"
set "EXIT_CODE=%ERRORLEVEL%"

popd
exit /b %EXIT_CODE%
