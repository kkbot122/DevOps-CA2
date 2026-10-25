[CmdletBinding()]
param(
    [ValidateSet('SourceDeploy','Monitoring','Ansible','Verify','Access','All')]
    [string]$Stage = 'All',
    [string]$Context = 'docker-desktop',
    [string]$Kubeconfig = (Join-Path $env:USERPROFILE '.kube/config')
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo
$runtime = Join-Path $repo '.runtime'
New-Item -ItemType Directory -Force $runtime, 'docs/evidence/windows' | Out-Null
$python = Join-Path $repo '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}
$kubeArgs = @('--kubeconfig', $Kubeconfig, '--context', $Context)
function Kube {
    param([string[]]$Arguments)
    & kubectl @kubeArgs @Arguments
    if ($LASTEXITCODE -ne 0) { throw "kubectl failed: $($Arguments -join ' ')" }
}
function Python {
    param([string[]]$Arguments)
    & $python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python failed: $($Arguments -join ' ')" }
}
Kube @('get', 'nodes')
if ($Stage -in @('SourceDeploy','All')) {
    Python @('scripts/package_app.py', '--output', '.runtime/app-source.tar.gz')
    Kube @('apply', '-f', 'k8s/00-namespace.yaml')
    $sourceManifest = & kubectl @kubeArgs -n urlshortener create configmap shortly-app-source --from-file=app-source.tar.gz=.runtime/app-source.tar.gz --dry-run=client -o yaml
    if ($LASTEXITCODE -ne 0) { throw 'Source ConfigMap generation failed' }
    $sourceManifest | & kubectl @kubeArgs apply -f -
    if ($LASTEXITCODE -ne 0) { throw 'Source ConfigMap apply failed' }
    $secretManifest = & kubectl @kubeArgs -n urlshortener create secret generic shortly-secrets --from-literal=ADMIN_TOKEN=demo-admin-token --dry-run=client -o yaml
    if ($LASTEXITCODE -ne 0) { throw 'Demo secret generation failed' }
    $secretManifest | & kubectl @kubeArgs apply -f -
    if ($LASTEXITCODE -ne 0) { throw 'Demo secret apply failed' }
    $appManifest = & kubectl @kubeArgs kustomize --load-restrictor LoadRestrictionsNone k8s/overlays/source-demo
    if ($LASTEXITCODE -ne 0) { throw 'Kustomize render failed' }
    $appManifest | & kubectl @kubeArgs apply -f -
    if ($LASTEXITCODE -ne 0) { throw 'Kubernetes apply failed' }
    Kube @('-n','urlshortener','rollout','status','deployment/shortly','--timeout=180s')
}
if ($Stage -in @('Monitoring','All')) {
    $helmCommand = Get-Command helm -ErrorAction SilentlyContinue
    if ($helmCommand) { $helm = $helmCommand.Source } else {
        $helmDir = Join-Path $runtime 'helm'
        New-Item -ItemType Directory -Force $helmDir | Out-Null
        $helm = Join-Path $helmDir 'windows-amd64/helm.exe'
        if (-not (Test-Path -LiteralPath $helm)) {
            $archive = Join-Path $helmDir 'helm.zip'
            $checksum = Join-Path $helmDir 'helm.sha256sum'
            Invoke-WebRequest 'https://get.helm.sh/helm-v4.2.2-windows-amd64.zip' -OutFile $archive
            Invoke-WebRequest 'https://get.helm.sh/helm-v4.2.2-windows-amd64.zip.sha256sum' -OutFile $checksum
            $expected = ((Get-Content -LiteralPath $checksum -Raw).Trim() -split '\s+')[0]
            if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ine $expected) { throw 'Helm checksum mismatch' }
            Expand-Archive -LiteralPath $archive -DestinationPath $helmDir -Force
        }
    }
    & $helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update
    if ($LASTEXITCODE -ne 0) { throw 'Helm repository setup failed' }
    & $helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack --version 91.8.2 --kubeconfig $Kubeconfig --kube-context $Context -n monitoring --create-namespace -f monitoring/kube-prometheus-stack-values.yaml --wait --timeout 10m
    if ($LASTEXITCODE -ne 0) { throw 'Monitoring installation failed' }
    Kube @('apply','--server-side','-k','monitoring')
}
if ($Stage -in @('Ansible','All')) {
    Python @('scripts/package_ansible.py','--output','.runtime/ansible-source.tar.gz')
    $sourceManifest = & kubectl @kubeArgs -n urlshortener create configmap shortly-ansible-source --from-file=ansible-source.tar.gz=.runtime/ansible-source.tar.gz --dry-run=client -o yaml
    if ($LASTEXITCODE -ne 0) { throw 'Ansible ConfigMap generation failed' }
    $sourceManifest | & kubectl @kubeArgs apply -f -
    if ($LASTEXITCODE -ne 0) { throw 'Ansible ConfigMap apply failed' }
    # This exact Job is a disposable target created by this repository.
    Kube @('-n','urlshortener','delete','job','shortly-ansible-demo','--ignore-not-found')
    Kube @('apply','-f','ansible/kubernetes-demo-job.yaml')
    $deadline = (Get-Date).AddMinutes(20)
    do {
        Start-Sleep -Seconds 5
        $jobText = & kubectl @kubeArgs -n urlshortener get job shortly-ansible-demo -o json
        if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect Ansible Job' }
        $job = $jobText | ConvertFrom-Json
        if ($job.status.failed -gt 0 -or $job.status.succeeded -gt 0) { break }
    } while ((Get-Date) -lt $deadline)
    & kubectl @kubeArgs -n urlshortener logs job/shortly-ansible-demo | Tee-Object -FilePath docs/evidence/windows/ansible-run.txt
    if ($LASTEXITCODE -ne 0 -or $job.status.succeeded -ne 1) { throw 'Ansible verification failed; see docs/evidence/windows/ansible-run.txt' }
}
if ($Stage -in @('Verify','All')) {
    Kube @('-n','urlshortener','get','deploy,pods,svc,hpa,pdb','-o','wide')
    Kube @('-n','monitoring','get','pods')
    Write-Host 'API smoke check (while the app port-forward is running):'
    Write-Host 'python scripts/verify_live.py --base http://127.0.0.1:18080 --output docs/evidence/windows/kubernetes-smoke.json'
}
if ($Stage -eq 'Access') {
    Write-Host 'Run each command in a separate terminal and leave it running:'
    Write-Host "kubectl --context $Context -n urlshortener port-forward service/shortly 18080:80"
    Write-Host "kubectl --context $Context -n monitoring port-forward service/kube-prometheus-stack-grafana 13000:80"
    Write-Host "kubectl --context $Context -n monitoring port-forward service/kube-prometheus-stack-prometheus 19090:9090"
}
Write-Host 'Stage completed.' -ForegroundColor Green
