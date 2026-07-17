internal static class AnnSetupLauncher
{
    private static int Main(string[] args)
    {
        return AnnPowerShellLauncher.Run("install_ann.ps1", args);
    }
}
