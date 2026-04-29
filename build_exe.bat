@echo off
setlocal
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
pyinstaller --noconfirm --onefile --windowed --name OCRJuridico app.py
echo.
echo EXE gerado em dist\OCRJuridico.exe
pause
