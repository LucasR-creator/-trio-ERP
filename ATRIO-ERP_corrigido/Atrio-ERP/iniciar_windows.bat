@echo off
setlocal
cd /d "%~dp0"
title ATRIO ERP - Servidor local

echo.
echo  ===========================================
echo       ATRIO  ^|  GESTAO EMPRESARIAL
 echo  ===========================================
echo.

if exist ".venv\Scripts\python.exe" goto dependencias

where py >nul 2>&1
if not errorlevel 1 (
  py -3 -m venv .venv
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo ERRO: Python nao foi encontrado.
    echo Instale o Python 3.11 ou mais recente em https://www.python.org/downloads/
    pause
    exit /b 1
  )
  python -m venv .venv
)
if errorlevel 1 (
  echo ERRO: Nao foi possivel criar o ambiente Python.
  pause
  exit /b 1
)

:dependencias
if exist ".venv\.atrio_ready" goto iniciar

echo Instalando bibliotecas na primeira execucao...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERRO: Falha ao instalar as bibliotecas. Confira sua conexao com a internet.
  pause
  exit /b 1
)
echo ok> ".venv\.atrio_ready"

:iniciar
echo.
echo Site:       http://127.0.0.1:8000
echo Painel:     http://127.0.0.1:8000/painel
echo.
echo Abra um dos enderecos no navegador e mantenha esta janela aberta.
echo Para encerrar, pressione Ctrl+C.
echo.
".venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000
pause
