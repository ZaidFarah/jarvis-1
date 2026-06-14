@echo off
setlocal

set "ROOT=%~dp0"
set "EXE=%ROOT%dist\Jarvis\Jarvis.exe"

if not exist "%EXE%" (
    echo Jarvis executable not found: %EXE%
    echo Run build_exe.bat first.
    exit /b 1
)

"%EXE%" %*
exit /b %ERRORLEVEL%
