@echo off
set ROOT=%~dp0..\..
set PYTHONPATH=%ROOT%\.agents;%PYTHONPATH%
python -m agentos.cli %*
