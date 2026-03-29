@echo off
:: Double-click to run the Zoning Assessment app (same pattern as solar-forecasting-tool ARECO65.bat)
setlocal
cd /d "%~dp0"
set "PY_EMBED_URL=https://www.python.org/ftp/python/3.12.9/python-3.12.9-embed-amd64.zip"
set "PY_EMBED_DIR=%~dp0.python"
set "PY_EMBED_ZIP=%~dp0py_embed.zip"

where python >nul 2>nul
if %errorlevel% equ 0 (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
  if %errorlevel% equ 0 goto run
)
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
  if %errorlevel% equ 0 (
    py -3 -m pip install -q -r "%~dp0requirements.txt" 2>nul
    py -3 "%~dp0run_zoning.py"
    goto end
  )
)

if exist "%PY_EMBED_DIR%\python.exe" goto run_embed

echo Python 3.10+ not found. Downloading portable Python (one-time)...
curl -sL -o "%PY_EMBED_ZIP%" "%PY_EMBED_URL%"
if not exist "%PY_EMBED_ZIP%" goto no_curl
for %%A in ("%PY_EMBED_ZIP%") do if %%~zA lss 1000000 goto no_curl

if not exist "%PY_EMBED_DIR%" mkdir "%PY_EMBED_DIR%"
tar -xf "%PY_EMBED_ZIP%" -C "%PY_EMBED_DIR%" 2>nul
if not exist "%PY_EMBED_DIR%\python.exe" (
  powershell -NoProfile -Command "Expand-Archive -Path '%PY_EMBED_ZIP%' -DestinationPath '%PY_EMBED_DIR%' -Force" 2>nul
)
if exist "%PY_EMBED_DIR%\python.exe" (
  del "%PY_EMBED_ZIP%" 2>nul
  goto run_embed
)
for /d %%D in ("%PY_EMBED_DIR%\python-*") do (
  move "%%~D\*" "%PY_EMBED_DIR%\"
  rmdir "%%~D" 2>nul
)
del "%PY_EMBED_ZIP%" 2>nul
if exist "%PY_EMBED_DIR%\python.exe" goto run_embed

:no_curl
echo.
echo Could not find Python. Install Python 3.10+ from https://www.python.org/downloads/
echo Then run this script again or:  python run_zoning.py
pause
exit /b 1

:run
python -m pip install -q -r "%~dp0requirements.txt" 2>nul
python "%~dp0run_zoning.py"
goto end

:run_embed
"%PY_EMBED_DIR%\python.exe" -m pip install -q -r "%~dp0requirements.txt" 2>nul
"%PY_EMBED_DIR%\python.exe" "%~dp0run_zoning.py"
goto end

:end
endlocal
