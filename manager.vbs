' Production Hub - tray launcher (no console at all).
' Double-click this (or put a shortcut in shell:startup) to run manager.py via
' pythonw.exe with NO console window. Unlike a .bat, a .vbs has no cmd host
' window, so nothing flashes. Manager hides to the system tray; right-click the
' tray icon to show the window or fully quit.
Option Explicit

Dim shell, fso, root, pyw
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)

pyw = root & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pyw) Then pyw = "pythonw"

shell.CurrentDirectory = root
' 0 = hidden window, False = do not wait
shell.Run """" & pyw & """ manager.py", 0, False
