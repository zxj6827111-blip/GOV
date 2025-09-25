# GovBudgetChecker 启动脚本

Write-Host "=== GovBudgetChecker 服务启动 ===" -ForegroundColor Green
Write-Host ""

# 检查.env文件
if (Test-Path ".env") {
    Write-Host "✅ 发现.env配置文件" -ForegroundColor Green
} else {
    Write-Host "⚠️  未发现.env文件，使用默认配置" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🚀 正在启动服务..." -ForegroundColor Cyan

# 启动后端API服务（端口8000）
Write-Host "1️⃣ 启动后端API服务（端口8000）..."
Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload" -NoNewWindow

# 等待2秒
Start-Sleep -Seconds 2

# 启动AI抽取器服务v2.0（端口9009）
Write-Host "2️⃣ 启动AI抽取器服务v2.0（端口9009）..."
Start-Process -FilePath "python" -ArgumentList "ai_extractor_service_v2.py" -NoNewWindow

# 等待3秒
Start-Sleep -Seconds 3

# 启动前端服务（端口3000）
Write-Host "3️⃣ 启动前端服务（端口3000）..."
Start-Process -FilePath "cmd" -ArgumentList "/c", "cd app && npm run dev" -NoNewWindow

Write-Host ""
Write-Host "🎉 所有服务启动完成！" -ForegroundColor Green
Write-Host ""
Write-Host "服务访问地址：" -ForegroundColor Cyan
Write-Host "  📱 前端应用: http://localhost:3000" -ForegroundColor White
Write-Host "  🔧 后端API: http://localhost:8000" -ForegroundColor White  
Write-Host "  🤖 AI服务: http://localhost:9009" -ForegroundColor White
Write-Host ""
Write-Host "💡 小贴士：" -ForegroundColor Yellow
Write-Host "  - 如遇到端口占用，请先关闭相关进程" -ForegroundColor Gray
Write-Host "  - 访问前端应用时，AI辅助功能应该已启用" -ForegroundColor Gray
Write-Host "  - 如仍显示'AI服务未启用'，请检查AI服务连通性" -ForegroundColor Gray
Write-Host ""