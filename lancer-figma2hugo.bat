@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON_EXE="

if exist "%ROOT%\.venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%ROOT%\venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT%\venv\Scripts\python.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=python"

set "PYTHONPATH=%ROOT%src;%PYTHONPATH%"
set "FIGMA2HUGO_HOME=%ROOT%"

"%PYTHON_EXE%" -c "from figma2hugo.gui import main; main()"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Le lancement de figma2hugo a echoue.
  echo Verifie que les dependances du projet sont installees.
  echo.
  pause
)

exit /b %EXIT_CODE%
