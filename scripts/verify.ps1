<#!
.SYNOPSIS
    Verify pip and npm connectivity under the current proxy configuration.
.DESCRIPTION
    Prints pip/npm versions, attempts to install lightweight packages via
    temporary directories, and reports whether network access works as expected.
#>

$ErrorActionPreference = 'Stop'

function New-TempDirectory {
    $path = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Path $path -Force | Out-Null
    return $path
}

function Remove-IfExists {
    param([string]$Path)
    if ($Path -and (Test-Path -LiteralPath $Path)) {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "=== pip status ==="
$pipOk = $false
try {
    $pipVersion = & pip --version
    Write-Host $pipVersion

    $pipTemp = New-TempDirectory
    try {
        Write-Host "Testing pip install via proxy..."
        & pip install `
            --no-input `
            --disable-pip-version-check `
            --no-cache-dir `
            --quiet `
            --target $pipTemp `
            colorama==0.4.6 | Out-Null
        $pipOk = $true
        Write-Host "pip connectivity: OK"
    } finally {
        Remove-IfExists -Path $pipTemp
    }
} catch {
    Write-Warning "pip check failed: $($_.Exception.Message)"
}

Write-Host "=== npm status ==="
$npmOk = $false
try {
    $npmVersion = & npm --version
    Write-Host "npm version $npmVersion"

    $npmTemp = New-TempDirectory
    try {
        Write-Host "Testing npm install via proxy..."
        & npm install is-number@7.0.0 `
            --prefix $npmTemp `
            --global-style `
            --no-progress `
            --foreground-scripts | Out-Null
        $npmOk = $true
        Write-Host "npm connectivity: OK"
    } finally {
        Remove-IfExists -Path $npmTemp
    }
} catch {
    Write-Warning "npm check failed: $($_.Exception.Message)"
}

if ($pipOk -and $npmOk) {
    Write-Host "✅ All connectivity checks passed."
    exit 0
} elseif ($pipOk -or $npmOk) {
    Write-Warning "Partial success. Please review the failed manager output above."
    exit 2
} else {
    Write-Error "❌ Both pip and npm connectivity checks failed."
    exit 1
}
