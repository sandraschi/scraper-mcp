!macro KillFleetProcesses
  DetailPrint "Stopping scraper-mcp MCP processes..."
  ExecWait 'powershell -NoProfile -Command "Stop-Process -Name scraper-mcp-backend -Force -ErrorAction SilentlyContinue; Stop-Process -Name scraper_mcp-native -Force -ErrorAction SilentlyContinue; taskkill /F /IM scraper-mcp-backend.exe /T 2>`; taskkill /F /IM scraper_mcp-native.exe /T 2>`"' $0
  !if "" == "currentUser"
    nsis_tauri_utils::KillProcessCurrentUser "scraper-mcp-backend.exe"
    Pop $0
    nsis_tauri_utils::KillProcessCurrentUser "scraper_mcp-native.exe"
    Pop $0
  !else
    nsis_tauri_utils::KillProcess "scraper-mcp-backend.exe"
    Pop $0
    nsis_tauri_utils::KillProcess "scraper_mcp-native.exe"
    Pop $0
  !endif
  Sleep 3000
!macroend

!macro UninstallPrevious
  DetailPrint "Checking for previous installation..."
  !if "" == "currentUser"
    ReadRegStr $R0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ai.fleet.scraper-mcp" "UninstallString"
  !else
    ReadRegStr $R0 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\ai.fleet.scraper-mcp" "UninstallString"
  !endif
  ${If} $R0 != ""
    DetailPrint "Removing previous installation..."
    ExecWait '"$R0" /S' $0
    DetailPrint "Previous uninstall exit code: $0"
    Sleep 1500
  ${EndIf}
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro KillFleetProcesses
  !insertmacro UninstallPrevious
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro KillFleetProcesses
!macroend
