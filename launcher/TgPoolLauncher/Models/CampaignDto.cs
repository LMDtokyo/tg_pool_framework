using System.Text.Json.Serialization;

namespace TgPoolLauncher.Models;

public sealed class CampaignStartRequest
{
    [JsonPropertyName("target")]
    public string Target { get; init; } = "";

    [JsonPropertyName("message")]
    public string Message { get; init; } = "";

    [JsonPropertyName("media_path")]
    public string? MediaPath { get; init; }

    [JsonPropertyName("buttons_raw")]
    public string? ButtonsRaw { get; init; }

    [JsonPropertyName("parse_mode")]
    public string? ParseMode { get; init; } = "markdown";
}

public sealed class CampaignStartResponse
{
    [JsonPropertyName("campaign_id")]
    public string CampaignId { get; init; } = "";

    [JsonPropertyName("started")]
    public bool Started { get; init; }
}

public sealed class CampaignStatusDto
{
    [JsonPropertyName("running")]
    public bool Running { get; init; }

    [JsonPropertyName("campaign_id")]
    public string? CampaignId { get; init; }

    [JsonPropertyName("target")]
    public string? Target { get; init; }

    [JsonPropertyName("total")]
    public int Total { get; init; }

    [JsonPropertyName("sent")]
    public int Sent { get; init; }

    [JsonPropertyName("failed")]
    public int Failed { get; init; }

    [JsonPropertyName("per_account")]
    public Dictionary<string, int> PerAccount { get; init; } = new();

    [JsonPropertyName("finished")]
    public bool Finished { get; init; }

    [JsonPropertyName("error")]
    public string? Error { get; init; }
}
