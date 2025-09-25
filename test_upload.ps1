# 测试文件上传和AI检测功能

Write-Host "=== GovBudgetChecker AI检测测试 ===" -ForegroundColor Green
Write-Host ""

# 测试服务状态
Write-Host "1. 检查服务状态..." -ForegroundColor Cyan

# 检查后端API
try {
    $apiHealth = Invoke-RestMethod -Uri "http://localhost:8000/api/health" -Method GET
    Write-Host "  ✅ 后端API状态: $($apiHealth.status)" -ForegroundColor Green
} catch {
    Write-Host "  ❌ 后端API连接失败: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 检查AI服务
try {
    $aiHealth = Invoke-RestMethod -Uri "http://localhost:9009/health" -Method GET
    Write-Host "  ✅ AI服务状态: $($aiHealth.status)" -ForegroundColor Green
    Write-Host "  📊 可用模型数: $($aiHealth.ai_client.available_models)" -ForegroundColor Cyan
} catch {
    Write-Host "  ❌ AI服务连接失败: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "2. 模拟文件上传..." -ForegroundColor Cyan

# 准备测试文件
$testFile = "samples\bad\上海市普陀区规划和自然资源局 2024 年度部门决算.pdf"
if (-not (Test-Path $testFile)) {
    Write-Host "  ❌ 测试文件不存在: $testFile" -ForegroundColor Red
    exit 1
}

# 使用PowerShell的方式上传文件
try {
    $uri = "http://localhost:8000/upload"
    $filePath = Resolve-Path $testFile
    
    # 创建multipart/form-data
    $boundary = [System.Guid]::NewGuid().ToString()
    $LF = "`r`n"
    $fileName = [System.IO.Path]::GetFileName($filePath)
    
    $bodyLines = (
        "--$boundary",
        "Content-Disposition: form-data; name=`"file`"; filename=`"$fileName`"",
        "Content-Type: application/pdf$LF",
        [System.IO.File]::ReadAllText($filePath, [System.Text.Encoding]::GetEncoding("iso-8859-1")),
        "--$boundary--$LF"
    ) -join $LF
    
    $response = Invoke-RestMethod -Uri $uri -Method Post -ContentType "multipart/form-data; boundary=$boundary" -Body $bodyLines
    
    $jobId = $response.job_id
    Write-Host "  ✅ 文件上传成功! Job ID: $jobId" -ForegroundColor Green
    
    Write-Host ""
    Write-Host "3. 启动AI检测分析..." -ForegroundColor Cyan
    
    # 启动双模式分析（包含AI）
    $analysisPayload = @{
        use_local_rules = $true
        use_ai_assist = $true
        mode = "dual"
    } | ConvertTo-Json
    
    $analysisResponse = Invoke-RestMethod -Uri "http://localhost:8000/api/analyze2/$jobId" -Method Post -Body $analysisPayload -ContentType "application/json"
    
    Write-Host "  ✅ 分析请求已提交" -ForegroundColor Green
    Write-Host "  📈 AI问题数: $($analysisResponse.ai_findings.Count)" -ForegroundColor Cyan
    Write-Host "  📋 规则问题数: $($analysisResponse.rule_findings.Count)" -ForegroundColor Cyan
    Write-Host "  🔗 合并问题数: $($analysisResponse.merged.totals.total)" -ForegroundColor Cyan
    
    Write-Host ""
    Write-Host "4. 检查作业状态..." -ForegroundColor Cyan
    
    # 检查作业目录
    $jobDir = "jobs\$jobId"
    if (Test-Path $jobDir) {
        Write-Host "  ✅ 作业目录已创建: $jobDir" -ForegroundColor Green
        
        # 检查状态文件
        $statusFile = "$jobDir\status.json"
        if (Test-Path $statusFile) {
            $status = Get-Content $statusFile | ConvertFrom-Json
            Write-Host "  📊 作业状态: $($status.status)" -ForegroundColor Cyan
            Write-Host "  🔧 AI辅助: $($status.use_ai_assist)" -ForegroundColor Cyan
            Write-Host "  📑 模式: $($status.mode)" -ForegroundColor Cyan
        }
        
        # 列出所有生成的文件
        Write-Host "  📁 生成的文件:" -ForegroundColor Cyan
        Get-ChildItem $jobDir | ForEach-Object {
            Write-Host "    - $($_.Name)" -ForegroundColor Gray
        }
    } else {
        Write-Host "  ⚠️  作业目录未找到" -ForegroundColor Yellow
    }
    
    Write-Host "🎉 AI检测测试完成！" -ForegroundColor Green
    Write-Host "您可以在前端 http://localhost:3000 查看详细结果" -ForegroundColor Cyan
    
} catch {
    Write-Host "  ❌ 测试失败: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "错误详情:" -ForegroundColor Yellow
    Write-Host $_.Exception.ToString() -ForegroundColor Gray
}