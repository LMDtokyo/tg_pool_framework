using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace TgPoolLauncher.Services;

public sealed class CachedDefaultCredentials
{
    [JsonPropertyName("api_id")]
    public int ApiId { get; init; }

    [JsonPropertyName("api_hash")]
    public string ApiHash { get; init; } = "";
}

/// <summary>
/// Local cache of the operator-entered default api_id/api_hash (Data\default_credentials.json),
/// applied by the backend to bare .session drops with no .json companion. Same pattern as
/// LicenseCacheFile: persisted here, re-sent to the backend on every startup (see
/// App.xaml.cs) since env vars given to the backend process can't change after launch,
/// but the backend also accepts a live update via POST /accounts/default_credentials.
/// </summary>
public static class DefaultCredentialsCacheFile
{
    private const string FileName = "default_credentials.json";

    public static string PathIn(string dataDir) => Path.Combine(dataDir, FileName);

    public static CachedDefaultCredentials? TryLoad(string dataDir)
    {
        var path = PathIn(dataDir);
        if (!File.Exists(path))
            return null;
        try
        {
            return JsonSerializer.Deserialize<CachedDefaultCredentials>(File.ReadAllText(path));
        }
        catch (Exception ex) when (ex is JsonException or IOException)
        {
            return null;
        }
    }

    public static void Save(string dataDir, CachedDefaultCredentials credentials)
    {
        Directory.CreateDirectory(dataDir);
        File.WriteAllText(PathIn(dataDir), JsonSerializer.Serialize(credentials));
    }
}
