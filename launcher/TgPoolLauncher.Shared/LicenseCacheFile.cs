using System.Text.Json;
using System.Text.Json.Serialization;

namespace TgPoolLauncher.Shared;

public sealed class CachedLicense
{
    [JsonPropertyName("license_key")]
    public string LicenseKey { get; init; } = "";

    [JsonPropertyName("hwid")]
    public string Hwid { get; init; } = "";

    [JsonPropertyName("tier")]
    public string Tier { get; init; } = "";

    [JsonPropertyName("expires_at")]
    public DateTimeOffset ExpiresAt { get; init; }
}

/// <summary>
/// Shared on-disk cache (Data\license.json) written by TgPoolActivator and
/// read by the WPF app. Only a local, no-network freshness check -- the
/// real enforcement is the local backend's periodic re-validation against
/// the central license server (src/licensing/service.py).
/// </summary>
public static class LicenseCacheFile
{
    private const string FileName = "license.json";

    public static string PathIn(string dataDir) => Path.Combine(dataDir, FileName);

    public static CachedLicense? TryLoad(string dataDir)
    {
        var path = PathIn(dataDir);
        if (!File.Exists(path))
            return null;
        try
        {
            return JsonSerializer.Deserialize<CachedLicense>(File.ReadAllText(path));
        }
        catch (Exception ex) when (ex is JsonException or IOException)
        {
            return null;
        }
    }

    public static void Save(string dataDir, CachedLicense license)
    {
        Directory.CreateDirectory(dataDir);
        File.WriteAllText(PathIn(dataDir), JsonSerializer.Serialize(license));
    }

    public static bool IsLocallyValid(CachedLicense? license) =>
        license is not null && license.ExpiresAt > DateTimeOffset.UtcNow;
}
