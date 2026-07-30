using System.Text.Json.Serialization;

namespace TgPoolLauncher.Models;

public sealed class ProxyCoverageDto
{
    [JsonPropertyName("total_accounts")]
    public int TotalAccounts { get; init; }

    [JsonPropertyName("unproxied_count")]
    public int UnproxiedCount { get; init; }

    [JsonPropertyName("unproxied_phones")]
    public List<string> UnproxiedPhones { get; init; } = [];

    [JsonPropertyName("shared_proxy_group_count")]
    public int SharedProxyGroupCount { get; init; }

    [JsonPropertyName("largest_shared_group_size")]
    public int LargestSharedGroupSize { get; init; }
}
