<#!
.SYNOPSIS
    Configure pip and npm proxy settings based on HTTP_PROXY/HTTPS_PROXY.
.DESCRIPTION
    Generates %APPDATA%\pip\pip.ini and repository root .npmrc files so that
    package managers respect the corporate proxy. Prints the resulting
    registry/proxy configuration for confirmation.
#>

$ErrorActionPreference = 'Stop'

if (-not $env:APPDATA) {
    throw 'APPDATA environment variable is not defined. Please run on Windows PowerShell.'
}

function New-ParentDirectory {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Path
    )

    $directory = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $directory)) {
        Write-Host "Creating directory: $directory"
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
}

$httpProxy  = $env:HTTP_PROXY
$httpsProxy = $env:HTTPS_PROXY
$pipIndexUrl = $env:PIP_INDEX_URL
$npmRegistry = $env:NPM_REGISTRY

$proxyForPip = if ($httpsProxy) { $httpsProxy } elseif ($httpProxy) { $httpProxy } else { $null }

$pipConfigPath = Join-Path $env:APPDATA 'pip\pip.ini'
New-ParentDirectory -Path $pipConfigPath

$pipConfig = "[global]`n"
if ($pipIndexUrl) {
    $pipConfig += "index-url = $pipIndexUrl`n"
}
if ($proxyForPip) {
    $pipConfig += "proxy = $proxyForPip`n"
} else {
    $pipConfig += "; proxy not configured (HTTP_PROXY/HTTPS_PROXY not set)`n"
}

Set-Content -LiteralPath $pipConfigPath -Value $pipConfig -Encoding UTF8

$repoRoot = Split-Path -Parent $PSScriptRoot
$npmrcPath = Join-Path $repoRoot '.npmrc'

$npmConfigLines = @()
if ($npmRegistry) {
    $npmConfigLines += "registry=$npmRegistry"
}
elseif (-not (Test-Path -LiteralPath $npmrcPath)) {
    # Respect npm default registry unless overridden.
    $npmConfigLines += "; registry not overridden"
}
if ($httpProxy) {
    $npmConfigLines += "proxy=$httpProxy"
}
if ($httpsProxy) {
    $npmConfigLines += "https-proxy=$httpsProxy"
}
if (-not $npmConfigLines) {
    $npmConfigLines += "; proxy not configured (HTTP_PROXY/HTTPS_PROXY not set)"
}

Set-Content -LiteralPath $npmrcPath -Value ($npmConfigLines -join "`n") -Encoding UTF8

Write-Host "✔ Generated pip config:" $pipConfigPath
Write-Host "    index-url:" ($pipIndexUrl ? $pipIndexUrl : '(pip default)')
Write-Host "    proxy:"     ($proxyForPip ? $proxyForPip : '(none)')

$effectiveRegistry = '(npm not available)'
try {
    if ($npmRegistry) {
        $effectiveRegistry = $npmRegistry
    } else {
        $effectiveRegistry = (& npm config get registry 2>$null)
    }
} catch {
    Write-Warning "npm command not found; skipping registry lookup."
}

Write-Host "✔ Generated npm config:" $npmrcPath
Write-Host "    registry:" $effectiveRegistry
Write-Host "    proxy:"     ($httpProxy ? $httpProxy : '(none)')
Write-Host "    https-proxy:" ($httpsProxy ? $httpsProxy : '(none)')
