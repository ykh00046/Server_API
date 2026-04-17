Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """" & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\start_services_hidden.bat""", 0, False
