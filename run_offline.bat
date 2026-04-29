@echo off
setlocal
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python app.py
if errorlevel 1 (
  echo.
  echo Falha ao iniciar. Verifique se as dependencias ja estao instaladas localmente.
)
pause
