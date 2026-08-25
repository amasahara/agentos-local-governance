@echo off
setlocal
set "ROOT=%~dp0\..\.."
set "AGENTOS_PROJECT_ROOT=%ROOT%"
set "PYTHONPATH=%ROOT%\.agents;%PYTHONPATH%"
python -m agentos.privileged_control_plane --root "%ROOT%" %*
exit /b %ERRORLEVEL%
