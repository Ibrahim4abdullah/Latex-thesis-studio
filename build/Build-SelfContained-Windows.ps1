$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Project = Split-Path -Parent $Root
$Runtime = Join-Path $Project "runtime"
$Tiny = Join-Path $Runtime "TinyTeX"
$Dist = Join-Path $Project "dist"

Write-Host "== LaTeX Thesis Studio self-contained Windows release =="

python -m pip install --upgrade pip
python -m pip install -r (Join-Path $Project "requirements.txt")

if (-not (Test-Path (Join-Path $Tiny "bin\windows\xelatex.exe"))) {
    New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
    Write-Host "Downloading current TinyTeX Windows bundle..."
    $release = Invoke-RestMethod "https://api.github.com/repos/rstudio/tinytex-releases/releases/latest"

    $asset = $release.assets | Where-Object {
        $_.name -match "^TinyTeX-.*windows.*\.exe$" -and $_.name -notmatch "^TinyTeX-[012]-"
    } | Select-Object -First 1

    if (-not $asset) {
        $asset = $release.assets | Where-Object { $_.name -match "TinyTeX.*windows.*\.exe$" } | Select-Object -First 1
    }
    if (-not $asset) { throw "Could not locate TinyTeX Windows asset." }

    $archive = Join-Path $Runtime $asset.name
    Invoke-WebRequest $asset.browser_download_url -OutFile $archive
    Write-Host "Extracting TinyTeX..."
    & $archive "-y" "-o$Runtime" | Out-Host

    if (-not (Test-Path $Tiny)) {
        $found = Get-ChildItem $Runtime -Directory | Where-Object { $_.Name -like "TinyTeX*" } | Select-Object -First 1
        if ($found) { Rename-Item $found.FullName $Tiny }
    }
    Remove-Item $archive -Force
}

$TexBin = Join-Path $Tiny "bin\windows"
$env:PATH = "$TexBin;$env:PATH"
$Tlmgr = Join-Path $TexBin "tlmgr.bat"
$Packages = @(
 "latexmk","biber","biblatex","biblatex-apa","csquotes",
 "fontspec","polyglossia","bidi","geometry","setspace","microtype","graphics","xcolor",
 "amsmath","amsfonts","mathtools","booktabs","tools","multirow","caption","float",
 "hyperref","url","enumitem","titlesec","tocloft","glossaries","acro","siunitx","algorithm2e",
 "etoolbox","xkeyval","kvoptions","graphics-cfg","pdfescape"
)

Write-Host "Ensuring thesis packages exist..."
& $Tlmgr option repository ctan | Out-Host
& $Tlmgr install $Packages | Out-Host

if (Test-Path $Dist) { Remove-Item $Dist -Recurse -Force }
Push-Location $Project
python -m PyInstaller --noconfirm --clean --windowed --name "LaTeX Thesis Studio" --collect-all PySide6 "app\main.py"
Pop-Location

$AppDist = Join-Path $Dist "LaTeX Thesis Studio"
New-Item -ItemType Directory -Force -Path (Join-Path $AppDist "runtime") | Out-Null
Copy-Item $Tiny (Join-Path $AppDist "runtime\TinyTeX") -Recurse -Force

$Zip = Join-Path $Dist "LaTeX-Thesis-Studio-v1.0-Windows-x64-Portable.zip"
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path "$AppDist\*" -DestinationPath $Zip -CompressionLevel Optimal

Write-Host ""
Write-Host "DONE"
Write-Host "Portable folder: $AppDist"
Write-Host "Portable ZIP: $Zip"
Write-Host "The end-user PC does NOT need Python, MiKTeX, or a separate TeX Live."
