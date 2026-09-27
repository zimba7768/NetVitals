param(
    [Parameter(Mandatory = $true)][string]$Interpreter,
    [Parameter(Mandatory = $true)][string]$Root
)

$root = $Root.TrimEnd('\')
$icon = Join-Path $root 'netvitals.ico'
$script = Join-Path $root 'main.py'

if (-not (Test-Path $script)) {
    Write-Host "  main.py not found in $root"
    exit 1
}

$desktop = [Environment]::GetFolderPath('Desktop')
$link = Join-Path $desktop 'NetVitals.lnk'

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = $Interpreter
$shortcut.Arguments = '"' + $script + '"'
$shortcut.WorkingDirectory = $root
$shortcut.Description = 'NetVitals network usage monitor'
if (Test-Path $icon) {
    $shortcut.IconLocation = $icon
} else {
    Write-Host "  netvitals.ico is missing, the shortcut will use the Python icon."
}
$shortcut.Save()

Write-Host "  Created: $link"
