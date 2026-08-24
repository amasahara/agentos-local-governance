@echo off
setlocal
REM File: .agents/bin/install.cmd
REM Purpose: Compatibility entry point for explicit AgentOS project bootstrap modes.
REM Responsibilities:
REM - Dispatch project-init and project-adopt to the current AgentOS runtime.
REM - Require an explicit target project and preserve its existing root files.
REM - Avoid recursive distribution copying and legacy installer semantics.

if "%~2"=="" goto usage

set "MODE=%~1"
set "PROJECT_ROOT=%~2"
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "DISTRIBUTION_ROOT=%%~fI"

if /I "%MODE%"=="project-init" goto project_init
if /I "%MODE%"=="project-adopt" goto project_adopt
goto unsupported

:project_init
if not "%~3"=="" goto usage
call "%SCRIPT_DIR%agentos.cmd" --root "%DISTRIBUTION_ROOT%" project-init --distribution-root "%DISTRIBUTION_ROOT%" --project-root "%PROJECT_ROOT%"
exit /b %ERRORLEVEL%

:project_adopt
if "%~3"=="" (
    call "%SCRIPT_DIR%agentos.cmd" --root "%DISTRIBUTION_ROOT%" project-adopt --distribution-root "%DISTRIBUTION_ROOT%" --project-root "%PROJECT_ROOT%"
    exit /b %ERRORLEVEL%
)
if /I "%~3"=="--apply" if /I "%~4"=="--human-confirmed" if "%~5"=="" (
    call "%SCRIPT_DIR%agentos.cmd" --root "%DISTRIBUTION_ROOT%" project-adopt --distribution-root "%DISTRIBUTION_ROOT%" --project-root "%PROJECT_ROOT%" --apply --human-confirmed
    exit /b %ERRORLEVEL%
)
goto usage

:unsupported
echo Unsupported mode: %MODE% 1>&2

:usage
echo Usage: 1>&2
echo   install.cmd project-init ^<project-root^> 1>&2
echo   install.cmd project-adopt ^<project-root^> [--apply --human-confirmed] 1>&2
exit /b 2
