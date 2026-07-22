using System;
using System.Diagnostics;
using System.IO;
using System.Text;

internal static class AnnPowerShellLauncher
{
    public static int Run(string scriptName, string[] args)
    {
        string baseDirectory = AppDomain.CurrentDomain.BaseDirectory;
        string scriptPath = Path.Combine(baseDirectory, scriptName);
        if (!File.Exists(scriptPath))
        {
            Console.Error.WriteLine("Required ANN installer script was not found: " + scriptPath);
            return 2;
        }

        string powershell = ResolvePowerShell();
        if (powershell.Length == 0)
        {
            Console.Error.WriteLine("PowerShell was not found on PATH.");
            return 3;
        }

        ProcessStartInfo startInfo = new ProcessStartInfo();
        startInfo.FileName = powershell;
        startInfo.Arguments = "-NoProfile -ExecutionPolicy Bypass -File " + Quote(scriptPath) + FormatArgs(args);
        startInfo.WorkingDirectory = baseDirectory;
        startInfo.UseShellExecute = false;
        startInfo.RedirectStandardOutput = false;
        startInfo.RedirectStandardError = false;
        startInfo.EnvironmentVariables["ANN_LAUNCHER_PID"] = Process.GetCurrentProcess().Id.ToString();

        using (Process process = Process.Start(startInfo))
        {
            if (process == null)
            {
                Console.Error.WriteLine("Failed to start PowerShell.");
                return 4;
            }
            process.WaitForExit();
            return process.ExitCode;
        }
    }

    private static string ResolvePowerShell()
    {
        string systemRoot = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
        string systemPowerShell = Path.Combine(systemRoot, "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
        if (File.Exists(systemPowerShell))
        {
            return systemPowerShell;
        }
        return "powershell.exe";
    }

    private static string FormatArgs(string[] args)
    {
        if (args == null || args.Length == 0)
        {
            return string.Empty;
        }
        StringBuilder builder = new StringBuilder();
        foreach (string arg in args)
        {
            builder.Append(' ');
            builder.Append(Quote(arg));
        }
        return builder.ToString();
    }

    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }
}
