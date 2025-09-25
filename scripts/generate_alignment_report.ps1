param(
  [string[]] $Jobs = @(
    "uploads/6207a48c197441630a7a62159700a257",
    "uploads/17ec68d5dc42c6eace2675dc38f3442c"
  )
)

$ErrorActionPreference = "Continue"

function Read-Json($path) {
  if (-not (Test-Path -LiteralPath $path)) { return $null }
  try {
    return Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
  } catch {
    Write-Host "⚠️ JSON解析失败: $path"
    return $null
  }
}

function Safe-ReadText($path) {
  if (-not (Test-Path -LiteralPath $path)) { return "" }
  try {
    return Get-Content -Raw -LiteralPath $path -Encoding UTF8
  } catch {
    Write-Host "⚠️ 文本读取失败: $path"
    return ""
  }
}

# “九张表”与别名（与模板一致）
$RequiredTables_Department = @(
  @{ name = "收入支出决算总表"; aliases = @("部门收支决算总表","收支决算总表","收入支出决算总表") },
  @{ name = "收入决算表"; aliases = @("部门收入决算表","收入决算表") },
  @{ name = "支出决算表"; aliases = @("部门支出决算表","支出决算表") },
  @{ name = "财政拨款收入支出决算总表"; aliases = @("财政拨款收支决算总表","财政拨款收入支出决算总表") },
  @{ name = "一般公共预算财政拨款支出决算表"; aliases = @("一般公共预算财政拨款支出决算表","一般公共预算支出决算表") },
  @{ name = "一般公共预算财政拨款基本支出决算表"; aliases = @("一般公共预算财政拨款基本支出决算表","基本支出决算表") },
  @{ name = "一般公共预算财政拨款“三公”经费支出决算表"; aliases = @("财政拨款“三公”经费支出决算表","三公经费支出决算表","“三公”经费支出决算表") },
  @{ name = "政府性基金预算财政拨款收入支出决算表"; aliases = @("政府性基金预算财政拨款收入支出决算表","政府性基金决算表") },
  @{ name = "国有资本经营预算财政拨款收入支出决算表"; aliases = @("国有资本经营预算财政拨款收入支出决算表","国有资本经营预算财政拨款支出决算表","国有资本经营支出决算表") }
)
$RequiredTables_Unit = @(
  @{ name = "收入支出决算总表"; aliases = @("单位收支决算总表","收支决算总表","收入支出决算总表") },
  @{ name = "收入决算表"; aliases = @("单位收入决算表","收入决算表") },
  @{ name = "支出决算表"; aliases = @("单位支出决算表","支出决算表") },
  @{ name = "财政拨款收入支出决算总表"; aliases = @("财政拨款收支决算总表","财政拨款收入支出决算总表") },
  @{ name = "一般公共预算财政拨款支出决算表"; aliases = @("一般公共预算财政拨款支出决算表","一般公共预算支出决算表") },
  @{ name = "一般公共预算财政拨款基本支出决算表"; aliases = @("一般公共预算财政拨款基本支出决算表","基本支出决算表") },
  @{ name = "一般公共预算财政拨款“三公”经费支出决算表"; aliases = @("财政拨款“三公”经费支出决算表","三公经费支出决算表","“三公”经费支出决算表") },
  @{ name = "政府性基金预算财政拨款收入支出决算表"; aliases = @("政府性基金预算财政拨款收入支出决算表","政府性基金决算表") },
  @{ name = "国有资本经营预算财政拨款收入支出决算表"; aliases = @("国有资本经营预算财政拨款收入支出决算表","国有资本经营预算财政拨款支出决算表","国有资本经营支出决算表") }
)
$ExplanationTitles_Department = @(
  "一、收入支出决算总体情况说明","二、收入决算情况说明","三、支出决算情况说明",
  "四、财政拨款收入支出决算总体情况说明",
  "六、一般公共预算财政拨款基本支出决算情况说明",
  "（一）“三公”经费财政拨款支出决算总体情况说明",
  "八、政府性基金预算财政拨款收入支出决算情况说明",
  "国有资本经营预算财政拨款收入支出决算情况说明"
)
$ExplanationTitles_Unit = @(
  "总体情况","收支总体情况说明","收入支出总体情况",
  "收入决算情况说明","收入情况说明","收入情况",
  "支出决算情况说明","支出情况说明","支出情况",
  "财政拨款总体情况说明","财政拨款总体情况",
  "基本支出情况说明","基本支出情况",
  "“三公”经费情况说明","三公经费总体情况说明",
  "政府性基金预算财政拨款收入支出决算情况说明","政府性基金情况说明",
  "国有资本经营预算财政拨款收入支出决算情况说明","国资经营情况说明"
)

# 输出目录
$reportDir = "reports"
if (-not (Test-Path -LiteralPath $reportDir)) { New-Item -ItemType Directory -Path $reportDir | Out-Null }

foreach ($jobDir in $Jobs) {
  try {
    Write-Host "== 处理: $jobDir"
    $absDir = (Get-Item -LiteralPath $jobDir -ErrorAction SilentlyContinue)?.FullName
    if (-not $absDir) { Write-Host "⚠️ 不存在，跳过：$jobDir"; continue }

    $statusPath = Join-Path $absDir "status.json"
    $textPath = Join-Path $absDir "extracted_text.txt"

    $status = Read-Json $statusPath
    if (-not $status) { Write-Host "⚠️ 未读取到 status.json"; }
    $text = Safe-ReadText $textPath
    if (-not $text) { Write-Host "⚠️ 未读取到 extracted_text.txt 或为空"; }

    $jobId = Split-Path $absDir -Leaf
    $origName = $null
    if ($status -and $status.result -and $status.result.meta) {
      $origName = $status.result.meta.original_filename
    }
    if (-not $origName) {
      $pdf = Get-ChildItem -LiteralPath $absDir -File -Filter *.pdf -ErrorAction SilentlyContinue | Select-Object -First 1
      $origName = $pdf?.Name
    }

    # 选择模板集合（通过文件名或猜测）
    $isDept = ($origName -like "*部门*" -or $origName -like "*附件2：部门*")
    $tables = $isDept ? $RequiredTables_Department : $RequiredTables_Unit
    $exps = $isDept ? $ExplanationTitles_Department : $ExplanationTitles_Unit
    $templateKey = $isDept ? "dept_decision_template_v1" : "unit_decision_template_district_v1"
    $templateName = $isDept ? "附件2：部门决算模板" : "附件2-2：单位决算公开模板（区级）"

    # 表命中检查
    $tableChecks = @()
    foreach ($t in $tables) {
      $names = @($t.name) + $t.aliases
      $hit = $false
      foreach ($n in $names) {
        if ($text -and ($text -match [regex]::Escape($n))) { $hit = $true; break }
      }
      $tableChecks += [pscustomobject]@{ table = $t.name; hit = $hit }
    }

    # 章节命中检查
    $expChecks = @()
    foreach ($title in $exps) {
      $hit = $false
      if ($text -and ($text -match [regex]::Escape($title))) { $hit = $true }
      $expChecks += [pscustomobject]@{ title = $title; hit = $hit }
    }

    # 问题统计
    $aiCount = 0; $ruleCount = 0; $legacyAll = 0
    if ($status) {
      if ($status.result) {
        if ($status.result.ai_findings) { $aiCount = @($status.result.ai_findings).Count }
        if ($status.result.rule_findings) { $ruleCount = @($status.result.rule_findings).Count }
        if ($status.result.issues -and $status.result.issues.all) { $legacyAll = @($status.result.issues.all).Count }
      } elseif ($status.ai_findings -or $status.rule_findings) {
        if ($status.ai_findings) { $aiCount = @($status.ai_findings).Count }
        if ($status.rule_findings) { $ruleCount = @($status.rule_findings).Count }
      }
    }

    $pages = $status?.result?.meta?.pages
    $filesize = $status?.result?.meta?.filesize
    $mode = $status?.result?.mode

    $okTables = ($tableChecks | Where-Object {$_.hit}).Count
    $totalTables = $tableChecks.Count
    $okExps = ($expChecks | Where-Object {$_.hit}).Count
    $totalExps = $expChecks.Count

    $report = @()
    $report += "# 模板对齐报告 - $templateName"
    $report += ""
    $report += "- Job ID: $jobId"
    $report += "- 原始文件: $origName"
    $report += "- 页面数: $pages"
    $report += "- 文件大小: $filesize"
    $report += "- 分析模式: $mode"
    $report += ""
    $report += "## 模板信息"
    $report += "- 模板Key: $templateKey"
    $report += "- 必备表格命中: $okTables / $totalTables"
    $report += "- 说明章节命中: $okExps / $totalExps"
    $report += ""
    $report += "## 表格命中详情"
    foreach ($c in $tableChecks) {
      $statusMark = $c.hit ? "✅" : "❌"
      $report += "- $statusMark $($c.table)"
    }
    $report += ""
    $report += "## 说明章节命中详情"
    foreach ($c in $expChecks) {
      $statusMark = $c.hit ? "✅" : "❌"
      $report += "- $statusMark $($c.title)"
    }
    $report += ""
    $report += "## 问题概览"
    $report += "- AI发现数: $aiCount"
    $report += "- 规则发现数: $ruleCount"
    if ($legacyAll -gt 0) { $report += "- 兼容汇总(all): $legacyAll" }
    $report += ""
    $report += "> 注：本文基于提取文本(extracted_text.txt)的关键字匹配进行对齐评估；正式一致性校验（数值勾稽、表-文一致等）由分析引擎在运行时完成。"

    $outPath = Join-Path $reportDir ("alignment_" + $jobId + ".md")
    $report -join "`r`n" | Out-File -FilePath $outPath -Encoding UTF8
    Write-Host "✅ 生成报告: $outPath"
  } catch {
    Write-Host "❌ 处理失败: $jobDir — $($_.Exception.Message)"
  }
}

Write-Host "== 完成。报告目录：$reportDir"