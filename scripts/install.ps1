# Official Windows installer for the checksum-verified wheel release.
# Download and inspect this file before executing it in a production environment.

$ErrorActionPreference = "Stop"
$repoUrl = if ($env:KITCLI_REPOSITORY) { $env:KITCLI_REPOSITORY } else { "https://github.com/zhouhanker/agent-kits" }
$releaseVersion = if ($env:KITCLI_VERSION) { $env:KITCLI_VERSION } else { "latest" }
$installRoot = if ($env:KITCLI_INSTALL_ROOT) { $env:KITCLI_INSTALL_ROOT } else { Join-Path $env:LOCALAPPDATA "kitcli" }
$binDir = if ($env:KITCLI_BIN_DIR) { $env:KITCLI_BIN_DIR } else { Join-Path $env:LOCALAPPDATA "Programs\kitcli" }

if (-not $repoUrl.StartsWith("https://")) { throw "KITCLI_REPOSITORY must use HTTPS" }
$python = $env:KITCLI_PYTHON
$pythonArgs = @()
if (-not $python) {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) { $python = $pyLauncher.Source; $pythonArgs = @("-3") }
    else { $python = (Get-Command python -ErrorAction SilentlyContinue).Source }
}
if (-not $python) { throw "Python 3.11+ is required" }
$pythonVersion = & $python @pythonArgs -c "import sys; print('%d.%d' % sys.version_info[:2])"
& $python @pythonArgs -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) { throw "Found Python $pythonVersion; Python 3.11+ is required" }

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("kitcli-install-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempRoot | Out-Null
try {
    if ($env:KITCLI_WHEEL_URL) {
        $wheelUrl = $env:KITCLI_WHEEL_URL
        $wheelName = if ($env:KITCLI_WHEEL_NAME) { $env:KITCLI_WHEEL_NAME } else { [System.IO.Path]::GetFileName(([uri]$wheelUrl).AbsolutePath) }
        $checksumUrl = $env:KITCLI_CHECKSUM_URL
        if (-not $checksumUrl) { throw "KITCLI_CHECKSUM_URL is required with KITCLI_WHEEL_URL" }
        $releaseApiUrl = if ($env:KITCLI_RELEASE_API_URL) { $env:KITCLI_RELEASE_API_URL } else { "" }
    }
    else {
        $repoPath = $repoUrl.Substring("https://github.com/".Length).TrimEnd("/")
        $apiUrl = if ($env:KITCLI_RELEASE_API_URL) { $env:KITCLI_RELEASE_API_URL } else { "https://api.github.com/repos/$repoPath/releases/latest" }
        if ($releaseVersion -ne "latest") { $apiUrl = "https://api.github.com/repos/$repoPath/releases/tags/$releaseVersion" }
        $release = Invoke-RestMethod -Uri $apiUrl -Headers @{ "User-Agent" = "kitcli-installer/1" }
        $wheel = @($release.assets | Where-Object { $_.name -match '^agent_kits-.+-py3-none-any\.whl$' })
        $checksum = @($release.assets | Where-Object { $_.name -eq "SHA256SUMS" })
        if ($wheel.Count -ne 1 -or $checksum.Count -ne 1) { throw "Release must contain one agent_kits wheel and SHA256SUMS" }
        $wheelName = $wheel[0].name
        $wheelUrl = $wheel[0].browser_download_url
        $checksumUrl = $checksum[0].browser_download_url
        $releaseApiUrl = $apiUrl
    }
    $wheelHost = ([uri]$wheelUrl).Host
    $checksumHost = ([uri]$checksumUrl).Host
    if (-not $wheelUrl.StartsWith("https://") -or -not $checksumUrl.StartsWith("https://") -or $wheelHost -notin @("github.com", "objects.githubusercontent.com") -or $checksumHost -notin @("github.com", "objects.githubusercontent.com")) { throw "Release asset URLs must use GitHub HTTPS" }
    $wheelPath = Join-Path $tempRoot $wheelName
    $checksumPath = Join-Path $tempRoot "SHA256SUMS"
    Invoke-WebRequest -Uri $wheelUrl -OutFile $wheelPath
    Invoke-WebRequest -Uri $checksumUrl -OutFile $checksumPath
    $line = Get-Content $checksumPath | Where-Object { $_ -match ([regex]::Escape($wheelName) + "$") } | Select-Object -First 1
    if (-not $line -or $line -notmatch "^([0-9a-fA-F]{64})\s+") { throw "Checksum missing for $wheelName" }
    $expected = $Matches[1].ToLowerInvariant()
    $actual = (Get-FileHash -Algorithm SHA256 -Path $wheelPath).Hash.ToLowerInvariant()
    if ($actual -ne $expected) { throw "SHA-256 verification failed" }

    New-Item -ItemType Directory -Force -Path $installRoot, $binDir | Out-Null
    $venv = Join-Path $installRoot "venv"
    $venvPython = Join-Path $venv "Scripts\python.exe"
    if (-not (Test-Path $venvPython)) { & $python @pythonArgs -m venv $venv }
    & $venvPython -m pip install --upgrade --no-deps $wheelPath | Out-Null
    $state = [ordered]@{
        schema_version = 1
        method = "official-isolated-installer"
        package = "agent-kits"
        python = $venvPython
        wheel_url = $wheelUrl
        checksum_url = $checksumUrl
        release_api_url = $releaseApiUrl
        install_root = $installRoot
        bin_dir = $binDir
    }
    $state | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $installRoot "install.json")
    $kitcli = Join-Path $venv "Scripts\kitcli.exe"
    Copy-Item $kitcli (Join-Path $binDir "kitcli.exe") -Force
    Copy-Item (Join-Path $venv "Scripts\agent-kits.exe") (Join-Path $binDir "agent-kits.exe") -Force
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $userPath) { $userPath = "" }
    if (-not (($userPath -split ";") -contains $binDir)) {
        [Environment]::SetEnvironmentVariable("Path", (($userPath.TrimEnd(";") + ";" + $binDir).TrimStart(";")), "User")
    }
    Write-Output "kitcli installed in $venv"
    Write-Output "Open a new terminal, then run: kitcli doctor"
}
finally {
    Remove-Item -Recurse -Force $tempRoot -ErrorAction SilentlyContinue
}
