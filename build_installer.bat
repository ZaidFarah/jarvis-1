@echo off
setlocal

set "ROOT=%~dp0"
pushd "%ROOT%" || exit /b 1

set "ISCC="
for %%I in (ISCC.exe) do set "ISCC=%%~$PATH:I"
if not defined ISCC (
    if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
)
if not defined ISCC (
    if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
)

if not defined ISCC (
    echo Inno Setup compiler not found. Install Inno Setup 6 first.
    popd
    exit /b 1
)

if not exist "dist\Jarvis\Jarvis.exe" (
    echo Missing dist\Jarvis\Jarvis.exe. Build the EXE first.
    popd
    exit /b 1
)

"%ISCC%" "installer\JarvisInstaller.iss"
set "EXIT_CODE=%ERRORLEVEL%"

popd
exit /b %EXIT_CODE%
