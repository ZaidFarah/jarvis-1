@echo off
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
pushd "%ROOT%" || exit /b 1

for /f "tokens=2" %%V in ('python main.py --version') do set "APP_VERSION=%%V"
if not defined APP_VERSION (
    echo Could not determine Jarvis version.
    popd
    exit /b 1
)

set "RELEASE_NAME=Jarvis-%APP_VERSION%-windows"
set "RELEASE_DIR=%ROOT%releases"
set "STAGING=%RELEASE_DIR%\%RELEASE_NAME%"
set "STAGING_DIST=%STAGING%\dist\Jarvis"
set "ZIP_PATH=%RELEASE_DIR%\%RELEASE_NAME%.zip"
set "DIST_DIR=%ROOT%dist\Jarvis"
set "EXE_PATH=%DIST_DIR%\Jarvis.exe"
set "INTERNAL_PATH=%DIST_DIR%\_internal"

if not exist "%INTERNAL_PATH%\" (
    if exist "%ROOT%dist\Jarvis_internal\" (
        set "INTERNAL_PATH=%ROOT%dist\Jarvis_internal"
    )
)

python main.py --release-package-check
if errorlevel 1 (
    echo Release package check failed. Build Jarvis before creating the release ZIP.
    popd
    exit /b 1
)

if not exist "%EXE_PATH%" (
    echo Missing %EXE_PATH%
    popd
    exit /b 1
)

if not exist "%INTERNAL_PATH%\" (
    echo Missing %INTERNAL_PATH%
    popd
    exit /b 1
)

if not exist "%RELEASE_DIR%" mkdir "%RELEASE_DIR%"

if exist "%STAGING%" (
    rmdir /s /q "%STAGING%"
)

if exist "%ZIP_PATH%" (
    del /q "%ZIP_PATH%"
)

mkdir "%STAGING%" || (
    echo Could not create staging directory %STAGING%
    popd
    exit /b 1
)

mkdir "%STAGING_DIST%" || (
    echo Could not create staging dist directory %STAGING_DIST%
    popd
    exit /b 1
)

copy "%EXE_PATH%" "%STAGING_DIST%\Jarvis.exe" >nul || goto :copy_failed
xcopy "%INTERNAL_PATH%" "%STAGING_DIST%\_internal\" /e /i /y >nul || goto :copy_failed
copy "%ROOT%README.md" "%STAGING%\README.md" >nul || goto :copy_failed
copy "%ROOT%run_jarvis.bat" "%STAGING%\run_jarvis.bat" >nul || goto :copy_failed
copy "%ROOT%run_jarvis_console.bat" "%STAGING%\run_jarvis_console.bat" >nul || goto :copy_failed
copy "%ROOT%test_packaged_app.bat" "%STAGING%\test_packaged_app.bat" >nul || goto :copy_failed

powershell -NoProfile -ExecutionPolicy Bypass -Command "$staging='%STAGING%'; $zip='%ZIP_PATH%'; Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $zip -Force"
set "ZIP_EXIT=%ERRORLEVEL%"
if not "%ZIP_EXIT%"=="0" (
    echo Failed to create %ZIP_PATH%
    popd
    exit /b %ZIP_EXIT%
)

rmdir /s /q "%STAGING%"
echo Created %ZIP_PATH%
popd
exit /b 0

:copy_failed
echo Failed to stage release files.
popd
exit /b 1
