# GovBudgetChecker AI版本 - 一键启动脚本
Write-Host "🚀 启动 GovBudgetChecker AI版本..." -ForegroundColor Green

# 检查当前目录
$currentDir = Get-Location
Write-Host "📁 当前目录: $currentDir" -ForegroundColor Yellow

# 1. 启动AI抽取器服务 (后台)
Write-Host "🤖 启动AI抽取器服务..." -ForegroundColor Cyan
Start-Process -FilePath "python" -ArgumentList "ai_extractor_service_v2.py" -WindowStyle Minimized

# 等待2秒
Start-Sleep -Seconds 2

# 2. 启动后端API服务 (后台)
Write-Host "🔧 启动后端API服务..." -ForegroundColor Cyan
Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload" -WindowStyle Minimized

# 等待3秒
Start-Sleep -Seconds 3

# 3. 启动前端服务 (后台)
Write-Host "📱 启动前端服务..." -ForegroundColor Cyan
Start-Process -FilePath "cmd" -ArgumentList "/c", "cd app && npm run dev" -WindowStyle Minimized

# 等待5秒让服务启动
Write-Host "⏳ 等待服务启动..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# 4. 检查服务状态
Write-Host "🔍 检查服务状态..." -ForegroundColor Green

try {
    $backendHealth = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -TimeoutSec 5
    Write-Host "✅ 后端API: 正常 (版本: $($backendHealth.version))" -ForegroundColor Green
} catch {
    Write-Host "❌ 后端API: 异常" -ForegroundColor Red
}

try {
    $aiHealth = Invoke-RestMethod -Uri "http://localhost:9009/health" -Method Get -TimeoutSec 15
    Write-Host "✅ AI服务: 正常 (模型数: $($aiHealth.ai_client.available_models))" -ForegroundColor Green
} catch {
    Write-Host "❌ AI服务: 异常 (可能仍在启动中)" -ForegroundColor Yellow
}

# 5. 打开浏览器
Write-Host "🌐 打开浏览器..." -ForegroundColor Cyan
Start-Process "http://localhost:3000"

Write-Host "🎉 启动完成!" -ForegroundColor Green
Write-Host "📱 前端地址: http://localhost:3000" -ForegroundColor White
Write-Host "🔧 后端API: http://localhost:8000" -ForegroundColor White
Write-Host "🤖 AI服务: http://localhost:9009" -ForegroundColor White

Write-Host "`n🧪 运行完整测试:" -ForegroundColor Yellow
Write-Host "python test_complete_flow.py" -ForegroundColor White

Write-Host "`n📊 查看进程状态:" -ForegroundColor Yellow
Write-Host "Get-Process | Where-Object {`$_.ProcessName -match 'python|node'}" -ForegroundColor White