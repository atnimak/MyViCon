@echo off
rem ============================================================
rem Сборка MyViCon в один .exe с иконкой (PyInstaller).
rem Требуется: pip install pyinstaller
rem
rem Иконку icon.ico положите рядом с этим файлом (в корень проекта).
rem Результат сборки: dist\MyViCon.exe
rem
rem ВАЖНО: mkvtoolnix НЕ включается в exe. Папку "mkvtoolnix"
rem (с mkvmerge.exe и mkvpropedit.exe) нужно положить РЯДОМ с
rem готовым MyViCon.exe. Программа по умолчанию ищет их в
rem <папка с exe>\mkvtoolnix\. Там же будет храниться
rem myvicon_config.json с настройками.
rem ============================================================

setlocal
cd /d "%~dp0"

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo PyInstaller ne naiden. Ustanovite ego komandoi:
    echo     pip install pyinstaller
    pause
    exit /b 1
)

if exist "icon.ico" (
    echo Sborka s ikonkoi icon.ico ...
    pyinstaller --noconfirm --clean --onefile --windowed --icon=icon.ico --name MyViCon --add-data "icon.ico;." app.py
) else (
    echo VNIMANIE: icon.ico ne naiden, exe budet sobran bez ikonki.
    pyinstaller --noconfirm --clean --onefile --windowed --name MyViCon app.py
)

echo.
if exist "dist\MyViCon.exe" (
    echo Gotovo: dist\MyViCon.exe
    echo Ne zabudte polozhit papku "mkvtoolnix" ryadom s MyViCon.exe.
) else (
    echo Sborka zavershilas s oshibkoi. Proverte vyvod vyshe.
)
pause
