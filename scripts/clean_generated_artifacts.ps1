param(
    [switch]$Apply,
    [switch]$TakeOwnership
)

# Mode simulation par defaut : sans -Apply, le script affiche seulement ce
# qu'il supprimerait. Le nettoyage reste donc sur avant un push.
$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Names = @(
    ".figma2hugo-scratch",
    ".figma2hugo-tmp",
    ".pytest-tmp",
    "site-check-live",
    "site-smoke",
    "site\public",
    "compare-probe"
)
$Names += Get-ChildItem -LiteralPath $Root -Directory -Name "tmp_pt_*" -ErrorAction SilentlyContinue
$Names += Get-ChildItem -LiteralPath $Root -Directory -Name "compare-*" -ErrorAction SilentlyContinue

$Removed = 0
$Failed = @()
foreach ($Name in $Names) {
    $Path = Join-Path $Root $Name
    if (-not (Test-Path -LiteralPath $Path)) {
        continue
    }
    $Resolved = (Resolve-Path -LiteralPath $Path).Path
    # Ne jamais supprimer hors du depot, meme si un glob ou un lien resout vers
    # un emplacement inattendu.
    if (-not $Resolved.StartsWith($Root)) {
        $Failed += [pscustomobject]@{ Path = $Resolved; Error = "Outside workspace" }
        continue
    }
    if (-not $Apply) {
        Write-Output $Resolved
        continue
    }
    try {
        Remove-Item -LiteralPath $Resolved -Recurse -Force
        $Removed++
    }
    catch {
        if ($TakeOwnership) {
            try {
                takeown /F $Resolved /R /D Y | Out-Null
                icacls $Resolved /grant "$env:USERNAME`:F" /T /C | Out-Null
                Remove-Item -LiteralPath $Resolved -Recurse -Force
                $Removed++
                continue
            }
            catch {
                $Failed += [pscustomobject]@{ Path = $Resolved; Error = $_.Exception.Message }
            }
        }
        else {
            $Failed += [pscustomobject]@{ Path = $Resolved; Error = $_.Exception.Message }
        }
    }
}

[pscustomobject]@{
    Requested = $Names.Count
    Removed = $Removed
    Failed = $Failed.Count
}
if ($Failed.Count -gt 0) {
    $Failed
    exit 1
}
