@echo off
setlocal

set "ROOT=%~dp0"
set "EXE=%ROOT%dist\Jarvis\Jarvis.exe"

if not exist "%EXE%" (
    echo Jarvis executable not found: %EXE%
    echo Run build_exe.bat first.
    exit /b 1
)

echo Running Jarvis packaged smoke checks...
echo.

"%EXE%" --runtime-check
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
"%EXE%" --health-check
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
"%EXE%" --openai-check
if errorlevel 1 exit /b %ERRORLEVEL%

if /i "%~1"=="--voice-command-test" (
    echo.
    echo Running optional voice command test...
    "%EXE%" --voice-command-test
    if errorlevel 1 exit /b %ERRORLEVEL%
) else if /i "%~1"=="--with-voice-command-test" (
    echo.
    echo Running optional voice command test...
    "%EXE%" --voice-command-test
    if errorlevel 1 exit /b %ERRORLEVEL%
) else (
    echo.
    echo Skipping voice command test. Pass --voice-command-test to enable it.
)

echo.
echo Packaged smoke checks completed.
exit /b 0
