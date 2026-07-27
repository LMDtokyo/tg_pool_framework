using System.Diagnostics;
using System.IO;
using TgPoolLauncher.Models;
using TgPoolLauncher.Shared;

namespace TgPoolLauncher.Services;

/// <summary>
/// Runs TgPoolActivator.exe -- a separate console process, not a WPF window --
/// as the license entry gate before MainWindow appears, then forwards the
/// resulting cached activation to the local backend once it's up so its own
/// gate (src/api/license_gate.py) picks it up too.
/// </summary>
public static class LicenseGateway
{
    public static bool HasLocallyValidLicense(string dataDir)
    {
        var cached = LicenseCacheFile.TryLoad(dataDir);
        return LicenseCacheFile.IsLocallyValid(cached) && cached!.Hwid == HardwareId.Get();
    }

    /// <summary>Launches the activator in its own console window and blocks until it exits.</summary>
    public static async Task<bool> RunActivatorAsync(string repoRoot, string dataDir)
    {
        var exePath = ResolveActivatorExecutable(repoRoot);
        if (exePath is null)
            return false;

        using var process = Process.Start(new ProcessStartInfo
        {
            FileName = exePath,
            Arguments = $"--data-dir \"{dataDir}\"",
            UseShellExecute = true,
            WorkingDirectory = Path.GetDirectoryName(exePath),
        });
        if (process is null)
            return false;

        await process.WaitForExitAsync();
        return process.ExitCode == 0;
    }

    /// <summary>Forwards the cached activation to the now-running local backend. No-op if nothing is cached.</summary>
    public static async Task<LicenseStatusDto?> SyncBackendAsync(BackendClient backend, string dataDir)
    {
        var cached = LicenseCacheFile.TryLoad(dataDir);
        if (cached is null)
            return null;
        return await backend.ActivateLicenseAsync(cached.LicenseKey, cached.Hwid);
    }

    private static string? ResolveActivatorExecutable(string repoRoot)
    {
        string[] candidates =
        [
            Path.Combine(AppContext.BaseDirectory, "TgPoolActivator.exe"),
            Path.Combine(repoRoot, "launcher", "TgPoolActivator", "bin", "Release", "net10.0-windows", "TgPoolActivator.exe"),
            Path.Combine(repoRoot, "launcher", "TgPoolActivator", "bin", "Debug", "net10.0-windows", "TgPoolActivator.exe"),
        ];
        return candidates.FirstOrDefault(File.Exists);
    }
}
