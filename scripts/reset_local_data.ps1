param(
  [switch]$KillPython = $false
)

$ErrorActionPreference = "Stop"

function Timestamp {
  return (Get-Date).ToString("yyyyMMdd_HHmmss")
}

function Ensure-Dir([string]$Path) {
  if (!(Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

function Move-IfExists([string]$Path, [string]$DestDir) {
  if (Test-Path -LiteralPath $Path) {
    $leaf = Split-Path -Leaf $Path
    $dest = Join-Path $DestDir $leaf
    Write-Host "[MOVE] $Path -> $dest"
    Move-Item -LiteralPath $Path -Destination $dest -Force
  }
}

if ($KillPython) {
  Write-Host "[KILL] Stopping DrugAgent-related python processes..."
  try {
    $procs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
      Select-Object ProcessId, CommandLine
    foreach ($p in $procs) {
      $cmd = if ($p.CommandLine) { $p.CommandLine } else { "" }
      $cmdLower = $cmd.ToLowerInvariant()
      if ($cmdLower.Contains("run_autonomous.py") -or
          $cmdLower.Contains("run_agent.py") -or
          $cmdLower.Contains("streamlit") -or
          $cmdLower.Contains("interactive_menu.py")) {
        Write-Host "  taskkill PID $($p.ProcessId)"
        cmd.exe /c "taskkill /F /PID $($p.ProcessId)" | Out-Null
      }
    }
  } catch {
    Write-Host "[WARN] Could not enumerate/kill processes: $($_.Exception.Message)"
  }
}

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$backupRoot = Join-Path $root "data\_backup"
$ts = Timestamp
$backupDir = Join-Path $backupRoot $ts

Ensure-Dir $backupRoot
Ensure-Dir $backupDir

Write-Host "[BACKUP] $backupDir"

Move-IfExists (Join-Path $root "data\drugagent.db") $backupDir
Move-IfExists (Join-Path $root "data\mlflow.db") $backupDir
Move-IfExists (Join-Path $root "data\chroma") $backupDir
Move-IfExists (Join-Path $root "data\evidence") $backupDir
Move-IfExists (Join-Path $root "mlruns") $backupDir
Move-IfExists (Join-Path $root "output") $backupDir
Move-IfExists (Join-Path $root "data\dock_tmp") $backupDir
Move-IfExists (Join-Path $root "data\temp_docking") $backupDir
Move-IfExists (Join-Path $root "data\docked_poses") $backupDir

Ensure-Dir (Join-Path $root "data")
Ensure-Dir (Join-Path $root "data\chroma")
Ensure-Dir (Join-Path $root "data\dock_tmp")
Ensure-Dir (Join-Path $root "data\docked_poses")
Ensure-Dir (Join-Path $root "data\evidence\cache")
Ensure-Dir (Join-Path $root "output")

Write-Host ""
Write-Host "[OK] Local reset complete."
Write-Host "     Next: npx prisma db push"
Write-Host "     Then: python run_agent.py or python run_autonomous.py"
