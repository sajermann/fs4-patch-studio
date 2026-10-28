; NSIS hooks of the FS4 Patch Studio installer (Tauri installerHooks).
; Before removing the app: a patch installed in the game stays there, only the app can undo it.
!macro NSIS_HOOK_PREUNINSTALL
  IfSilent fs4_skip_notice
  ${If} $LANGUAGE == 1046
    MessageBox MB_OKCANCEL|MB_ICONINFORMATION "Se você instalou um patch no jogo pelo app, abra o FS4 Patch Studio e use 'Desinstalar patch' antes de remover o app: depois de removido, ele não consegue mais devolver o jogo ao original.$\r$\n$\r$\nContinuar com a desinstalação?" IDOK fs4_skip_notice
  ${Else}
    MessageBox MB_OKCANCEL|MB_ICONINFORMATION "If you installed a patch in the game with the app, open FS4 Patch Studio and use 'Uninstall patch' before removing the app: once removed, it can no longer restore the game to the original.$\r$\n$\r$\nContinue uninstalling?" IDOK fs4_skip_notice
  ${EndIf}
  Abort
  fs4_skip_notice:
!macroend

; The app keeps its data (project, originals, patch...) in data\ inside the app folder: removed only when the
; "delete app data" checkbox is checked, never on updates.
!macro NSIS_HOOK_POSTUNINSTALL
  ${If} $DeleteAppDataCheckboxState = 1
  ${AndIf} $UpdateMode <> 1
    RmDir /r "$INSTDIR\data"
    RmDir "$INSTDIR"
  ${EndIf}
!macroend
