internal static class AnnUninstallLauncher
{
    private static int Main(string[] args)
    {
        return AnnPowerShellLauncher.Run("uninstall_ann.ps1", args);
    }
}
