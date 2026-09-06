@echo off
rem Neon Coffee CLI launcher. Usage:  ncc <command> [args]
setlocal
set "PYTHONPATH=%~dp0tools\ncc;%PYTHONPATH%"
python -m ncc %*
