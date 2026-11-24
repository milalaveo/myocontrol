; Only an actual NSIS installation enables the installed-app updater.
!macro customInstall
  Push $0
  FileOpen $0 "$INSTDIR\resources\myocontrol-installed" w
  FileWrite $0 "nsis"
  FileClose $0
  Pop $0
!macroend
