@echo off
setlocal
set "SOURCE=%~dp0\..\.."
set "TARGET=%CD%"
xcopy "%SOURCE%\.agents" "%TARGET%\.agents\" /E /I /Y >nul
for %%F in (AGENTS.md README.md huong_dan.md VERSION) do (
  if not exist "%TARGET%\%%F" (
    copy "%SOURCE%\%%F" "%TARGET%\%%F" >nul
  ) else (
    copy "%SOURCE%\%%F" "%TARGET%\%%~nF.agentos%%~xF" >nul
    echo Preserved existing %%F; wrote AgentOS copy to %%~nF.agentos%%~xF.
  )
)
call "%TARGET%\.agents\bin\agentos.cmd" instruction-check || exit /b 2
call "%TARGET%\.agents\bin\agentos.cmd" docs-check || exit /b 2
call "%TARGET%\.agents\bin\agentos.cmd" db-status || exit /b 2
endlocal
