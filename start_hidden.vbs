' Production Hub - headless autostart (no console window).
' For a 24/7 ops PC: put a shortcut to this file in the Startup folder so
' API + Dashboard launch in the background on boot. Logs go to logs/.
' Stop with stop.bat.
Option Explicit

Dim shell, fso, root, py
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)

py = root & "\.venv\Scripts\python.exe"
If Not fso.FileExists(py) Then py = "python"

shell.CurrentDirectory = root
' 0 = hidden window, False = do not wait
shell.Run """" & py & """ -m uvicorn api.main:app --host 0.0.0.0 --port 8000", 0, False
shell.Run """" & py & """ -m streamlit run dashboard/app.py --server.address 0.0.0.0 --server.port 8502 --server.headless true", 0, False
