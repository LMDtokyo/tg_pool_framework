using System.Text.Json.Serialization;

namespace TgPoolLauncher.Models;

public sealed class LicenseActivateRequest
{
    [JsonPropertyName("license_key")]
    public string LicenseKey { get; init; } = "";

    [JsonPropertyName("hwid")]
    public string Hwid { get; init; } = "";
}

public sealed class LicenseStatusDto
{
    [JsonPropertyName("valid")]
    public bool Valid { get; init; }

    [JsonPropertyName("tier")]
    public string? Tier { get; init; }

    [JsonPropertyName("expires_at")]
    public DateTimeOffset? ExpiresAt { get; init; }

    [JsonPropertyName("reason")]
    public string Reason { get; init; } = "";
}
