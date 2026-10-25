[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo
$runtime = Join-Path $repo '.runtime'
New-Item -ItemType Directory -Force $runtime | Out-Null
Start-Transcript -Path (Join-Path $runtime 'prepare-images.log') -Force
function Run-Checked {
    param([string]$Program, [string[]]$Arguments)
    Write-Host ('> ' + $Program + ' ' + ($Arguments -join ' '))
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}
function Import-NodeImages {
    param([string]$NodeName, [string]$Archive)
    if ($NodeName -notmatch '^[a-z0-9][a-z0-9.-]*$') { throw "Invalid node name: $NodeName" }
    Write-Host "> Loading Dockerfile images into $NodeName via binary stdin"
    # PowerShell 5 pipes transcode binary data; stream directly to Docker instead.
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = (Get-Command docker -ErrorAction Stop).Source
    $start.Arguments = "exec -i $NodeName ctr --namespace k8s.io images import -"
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $inputFile = [System.IO.File]::OpenRead($Archive)
        try { $inputFile.CopyTo($process.StandardInput.BaseStream) }
        finally { $inputFile.Dispose(); $process.StandardInput.Close() }
        $process.WaitForExit()
        Write-Host $stdout.Result
        if ($stderr.Result) { Write-Host $stderr.Result }
        if ($process.ExitCode -ne 0) { throw "Image import into $NodeName failed with exit code $($process.ExitCode)" }
    } finally { $process.Dispose() }
}
try {
    Run-Checked docker @('info', '--format', '{{.ServerVersion}}')
    Run-Checked docker @('compose', 'up', '-d', '--build', '--wait')
    foreach ($release in @(@('v1', 'none'), @('v2', 'none'), @('v2-bad-crash', 'crash'))) {
        Run-Checked docker @('build', '-t', "shortly:$($release[0])", '--build-arg', "APP_VERSION=$($release[0])", '--build-arg', "BAD_RELEASE_MODE=$($release[1])", '.')
    }
    $archive = Join-Path $runtime 'shortly-images.tar'
    Run-Checked docker @('image', 'save', '-o', $archive, 'shortly:v1', 'shortly:v2', 'shortly:v2-bad-crash')
    $nodes = & kubectl --context docker-desktop get nodes -o 'jsonpath={.items[*].metadata.name}'
    if ($LASTEXITCODE -ne 0 -or -not $nodes) { throw 'Docker Desktop Kubernetes is not reachable or has no nodes.' }
    foreach ($nodeName in ($nodes -split '\s+')) {
        # Docker Desktop kind nodes have the same container and Kubernetes node name.
        & docker inspect $nodeName --format '{{.Name}}' 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Import-NodeImages -NodeName $nodeName -Archive $archive
        } else {
            throw "No Docker Desktop kind container for $nodeName. Import shortly:v1, shortly:v2 and shortly:v2-bad-crash with the image-loading command for your cluster runtime before deploying."
        }
    }
    Write-Host 'PASS: Dockerfile images built and imported. The Kubernetes rollout can now be started.' -ForegroundColor Green
} finally { Stop-Transcript }
