; Research OS uninstaller additions (electron-builder `nsis.include`).
; Before the files are removed, the backend takes back what its safe renderer added to this computer: the AppContainer profile
; `ros.render.sandbox.v1`, the folder permissions it was given and its private interpreter copy under <home>/render
; (`research-os-backend.exe --worker render-cleanup`, ros/lib/renderkit.py `cleanup`). The person's records are never touched.
; An update also runs the old uninstaller; then nothing is removed, because the new version uses the same renderer.
!macro customUnInstall
  ${ifNot} ${isUpdated}
    ${if} ${FileExists} "$INSTDIR\resources\backend\research-os-backend.exe"
      nsExec::ExecToLog '"$INSTDIR\resources\backend\research-os-backend.exe" --worker render-cleanup'
      Pop $0
    ${endIf}
  ${endIf}
!macroend
