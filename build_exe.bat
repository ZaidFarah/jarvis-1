@echo off
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
pushd "%ROOT%" || exit /b 1

python -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo PyInstaller is not installed. Run: python -m pip install -r requirements.txt
    popd
    exit /b 1
)

if exist build (
    rmdir /s /q build
)

if exist dist (
    rmdir /s /q dist
)

set "BASE_ARGS=--noconfirm --clean --onedir --console --name Jarvis --distpath dist --workpath build --specpath build"

if exist "%ROOT%assets\jarvis.ico" (
    if exist "%ROOT%assets" (
        python -m PyInstaller !BASE_ARGS! --add-data "%ROOT%.env.example;." --icon "%ROOT%assets\jarvis.ico" --add-data "%ROOT%assets;assets" main.py
    ) else (
        python -m PyInstaller !BASE_ARGS! --add-data "%ROOT%.env.example;." --icon "%ROOT%assets\jarvis.ico" main.py
    )
) else if exist "%ROOT%assets" (
    python -m PyInstaller !BASE_ARGS! --add-data "%ROOT%.env.example;." --add-data "%ROOT%assets;assets" main.py
) else (
    python -m PyInstaller !BASE_ARGS! --add-data "%ROOT%.env.example;." main.py
)
set "EXIT_CODE=%ERRORLEVEL%"

popd
exit /b %EXIT_CODE%
