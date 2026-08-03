using System.Text.Json.Serialization;

namespace TgPoolLauncher.Models;

public sealed class GitHubReleaseDto
{
    [JsonPropertyName("tag_name")]
    public string TagName { get; init; } = "";

    [JsonPropertyName("assets")]
    public List<GitHubReleaseAssetDto> Assets { get; init; } = new();
}

public sealed class GitHubReleaseAssetDto
{
    [JsonPropertyName("name")]
    public string Name { get; init; } = "";

    [JsonPropertyName("browser_download_url")]
    public string BrowserDownloadUrl { get; init; } = "";
}
