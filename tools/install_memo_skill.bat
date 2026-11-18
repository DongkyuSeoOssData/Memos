@echo off
chcp 65001 >nul
title Memos skill install
echo.
echo  Memos 메모 스킬 설치 중...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { $d=Join-Path $env:USERPROFILE '.claude\skills\memo-app'; New-Item -ItemType Directory -Force -Path (Join-Path $d 'scripts') | Out-Null; $u='https://raw.githubusercontent.com/DongkyuSeoOssData/Memos/main/.claude/skills/memo-app'; Invoke-WebRequest -UseBasicParsing ($u+'/SKILL.md') -OutFile (Join-Path $d 'SKILL.md'); Invoke-WebRequest -UseBasicParsing ($u+'/scripts/memos.py') -OutFile (Join-Path $d 'scripts\memos.py'); Write-Host (' [OK] ' + $d) } catch { Write-Host (' [FAIL] ' + $_.Exception.Message); exit 1 }"
if errorlevel 1 (echo. & echo  설치 실패. 위 메시지를 Claude에게 보여 주세요.) else (echo. & echo  설치 완료. Claude Code 어디서든 "내 메모 목록 보여 줘" 라고 해 보세요.)
echo.
pause
