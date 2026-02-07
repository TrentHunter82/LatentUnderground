Write-Host "Stopping swarm..." -ForegroundColor Yellow
Get-Process -Name "claude" -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Host "All Claude processes stopped." -ForegroundColor Green
Write-Host ""
Write-Host "Files preserved:" -ForegroundColor White
Write-Host "  tasks/TASKS.md    - Task progress" -ForegroundColor Gray
Write-Host "  tasks/lessons.md  - Accumulated lessons" -ForegroundColor Gray
Write-Host "  tasks/todo.md     - Agent plans" -ForegroundColor Gray
Write-Host "  progress.txt      - Learnings" -ForegroundColor Gray
Write-Host "  AGENTS.md         - Agent guidelines" -ForegroundColor Gray
Write-Host ""
Write-Host "Resume with: .\swarm.ps1 -Resume" -ForegroundColor Green
