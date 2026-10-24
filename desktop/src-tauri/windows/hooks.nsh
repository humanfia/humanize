; The installer's own steps, around Tauri's: Humanize Desktop goes in the Start menu alone, and on
; the desktop only where whoever installs it asks.

; The finish page offers a desktop shortcut, unticked.
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED

; A silent or passive install, which has no finish page, makes one regardless: taken back, unless
; this is an update keeping the one asked for before.
!macro NSIS_HOOK_POSTINSTALL
  ${If} $UpdateMode <> 1
    ${If} $PassiveMode = 1
    ${OrIf} ${Silent}
      Delete "$DESKTOP\${PRODUCTNAME}.lnk"
    ${EndIf}
  ${EndIf}
!macroend
