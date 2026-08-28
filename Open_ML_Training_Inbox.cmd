@echo off
set "ROOT=%~dp0"
if not exist "%ROOT%ml_workspace\historical_inbox" mkdir "%ROOT%ml_workspace\historical_inbox"
start "" "%ROOT%ml_workspace\historical_inbox"
