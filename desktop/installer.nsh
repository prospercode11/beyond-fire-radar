!macro customInstall
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Beyond Fire Radar" '"$INSTDIR\${APP_EXECUTABLE_FILENAME}" --background'
!macroend

!macro customUnInstall
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Beyond Fire Radar"
!macroend
