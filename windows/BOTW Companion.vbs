Option Explicit

Dim shell, fso, launcherDirectory, projectFile, projectRoot, pythonPath, command, exitCode
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

launcherDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
projectFile = fso.BuildPath(launcherDirectory, "project-root.txt")

If fso.FileExists(projectFile) Then
    Dim stream
    Set stream = fso.OpenTextFile(projectFile, 1, False, -1)
    projectRoot = Trim(stream.ReadAll)
    stream.Close
Else
    projectRoot = fso.GetParentFolderName(launcherDirectory)
End If

If Not fso.FileExists(fso.BuildPath(projectRoot, "pyproject.toml")) Then
    MsgBox "Le dossier BOTW Companion est introuvable. Relance l'installeur Windows depuis le clone du projet.", 16, "BOTW Companion"
    WScript.Quit 1
End If

pythonPath = fso.BuildPath(projectRoot, "runtime\pythonw.exe")
If Not fso.FileExists(pythonPath) Then pythonPath = fso.BuildPath(projectRoot, "python\pythonw.exe")
If Not fso.FileExists(pythonPath) Then pythonPath = fso.BuildPath(projectRoot, ".venv\Scripts\pythonw.exe")

If Not fso.FileExists(pythonPath) Then
    MsgBox "Python Windows est introuvable. Crée l'environnement .venv ou installe le runtime embarqué, puis relance l'installeur.", 16, "BOTW Companion"
    WScript.Quit 1
End If

shell.CurrentDirectory = projectRoot
command = Quote(pythonPath) & " -m botw_companion.windows_launcher --project " & Quote(projectRoot)
exitCode = shell.Run(command, 0, True)
WScript.Quit exitCode

Function Quote(value)
    Quote = Chr(34) & Replace(value, Chr(34), Chr(34) & Chr(34)) & Chr(34)
End Function