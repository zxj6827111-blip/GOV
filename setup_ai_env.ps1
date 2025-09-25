# GovBudgetChecker AI服务环境变量配置脚本 - v2.0

Write-Host "=== GovBudgetChecker AI服务配置 v2.0 ===" -ForegroundColor Green
Write-Host ""

# 设置AI辅助服务环境变量
$env:AI_ASSIST_ENABLED = "true"
$env:AI_EXTRACTOR_URL = "http://127.0.0.1:9009/ai/extract/v1"

# GLM和DeepSeek多模型容灾配置
# GLM-4.5-Flash配置 (主AI)
# $env:ZHIPU_FLASH_API_KEY = "your_zhipu_flash_api_key_here"
# $env:ZHIPU_FLASH_MODEL = "glm-4.5-flash"

# GLM-4.5配置 (备用AI)
# $env:ZHIPU_GLM45_API_KEY = "your_zhipu_glm45_api_key_here"
# $env:ZHIPU_GLM45_MODEL = "ZhipuAI/GLM-4.5"

# DeepSeek配置
# $env:DEEPSEEK_API_KEY = "your_deepseek_api_key_here"
# $env:DEEPSEEK_PRIMARY_MODEL = "deepseek-ai/DeepSeek-V3.1"
# $env:DEEPSEEK_BACKUP_MODEL = "deepseek-ai/DeepSeek-V3"

Write-Host "✅ AI服务环境变量已设置:" -ForegroundColor Green
Write-Host "   AI_ASSIST_ENABLED = $env:AI_ASSIST_ENABLED" -ForegroundColor Cyan
Write-Host "   AI_EXTRACTOR_URL = $env:AI_EXTRACTOR_URL" -ForegroundColor Cyan
Write-Host ""

Write-Host "⚠️  注意：这些环境变量仅在当前PowerShell会话中有效。" -ForegroundColor Yellow
Write-Host "   如需永久设置，请编辑.env文件或使用系统环境变量设置。" -ForegroundColor Yellow
Write-Host ""

Write-Host "🚀 现在可以启动AI抽取器服务v2.0了：" -ForegroundColor Green
Write-Host "   python ai_extractor_service_v2.py" -ForegroundColor Cyan
Write-Host ""

Write-Host "📝 然后启动后端服务：" -ForegroundColor Green  
Write-Host "   cd api && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload" -ForegroundColor Cyan