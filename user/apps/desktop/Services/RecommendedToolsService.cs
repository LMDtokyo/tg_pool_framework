using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using TgPoolLauncher.Models;

namespace TgPoolLauncher.Services;

/// <summary>
/// Checks the recommended third-party tools' official GitHub Releases for
/// their current version and downloads the matching Windows installer
/// straight into Data\Tools -- no mirroring on our own infrastructure (see
/// RecommendedToolRow's doc comment for why). A small JSON file next to the
/// downloads remembers which version was last fetched per tool, so a
/// previously-downloaded installer isn't silently treated as current forever.
/// </summary>
public sealed class RecommendedToolsService
{
    private readonly HttpClient _http;
    private readonly string _stateFilePath;

    public RecommendedToolsService(HttpClient http)
    {
        _http = http;
        if (_http.DefaultRequestHeaders.UserAgent.Count == 0)
            _http.DefaultRequestHeaders.UserAgent.Add(new ProductInfoHeaderValue("TgPoolLauncher", "1.0"));
        _stateFilePath = Path.Combine(AppPaths.Tools, "installed_versions.json");
    }

    public async Task<(string version, string assetUrl, string assetName)?> GetLatestReleaseAsync(
        string gitHubRepo, Func<string, bool> assetMatches, CancellationToken ct = default)
    {
        var release = await _http.GetFromJsonAsync<GitHubReleaseDto>(
            $"https://api.github.com/repos/{gitHubRepo}/releases/latest", ct);
        var asset = release?.Assets.FirstOrDefault(a => assetMatches(a.Name));
        if (release is null || asset is null)
            return null;
        return (release.TagName.TrimStart('v'), asset.BrowserDownloadUrl, asset.Name);
    }

    public string? GetInstalledVersion(string toolKey) =>
        LoadState().GetValueOrDefault(toolKey);

    public async Task<string> DownloadAsync(
        string toolKey, string assetUrl, string assetName, string version,
        IProgress<double> progress, CancellationToken ct = default)
    {
        var destPath = Path.Combine(AppPaths.Tools, assetName);
        using (var response = await _http.GetAsync(assetUrl, HttpCompletionOption.ResponseHeadersRead, ct))
        {
            response.EnsureSuccessStatusCode();
            var total = response.Content.Headers.ContentLength ?? -1;
            await using var source = await response.Content.ReadAsStreamAsync(ct);
            await using var dest = File.Create(destPath);
            var buffer = new byte[81920];
            long readTotal = 0;
            int read;
            while ((read = await source.ReadAsync(buffer, ct)) > 0)
            {
                await dest.WriteAsync(buffer.AsMemory(0, read), ct);
                readTotal += read;
                if (total > 0)
                    progress.Report((double)readTotal / total);
            }
        }

        var state = LoadState();
        state[toolKey] = version;
        SaveState(state);
        return destPath;
    }

    private Dictionary<string, string> LoadState()
    {
        try
        {
            if (File.Exists(_stateFilePath))
            {
                var json = File.ReadAllText(_stateFilePath);
                return JsonSerializer.Deserialize<Dictionary<string, string>>(json) ?? new();
            }
        }
        catch
        {
            // best-effort -- a corrupt cache just means every tool re-checks as not-downloaded
        }
        return new();
    }

    private void SaveState(Dictionary<string, string> state)
    {
        try
        {
            Directory.CreateDirectory(AppPaths.Tools);
            File.WriteAllText(_stateFilePath, JsonSerializer.Serialize(state));
        }
        catch
        {
            // best-effort -- the version just won't be remembered across restarts
        }
    }
}
