using System.Text.Json.Serialization;

namespace TgPoolLauncher.Models;

public sealed class ScheduledCampaignCreateRequest
{
    [JsonPropertyName("name")]
    public string Name { get; init; } = "";

    [JsonPropertyName("campaign_type")]
    public string CampaignType { get; init; } = "";

    [JsonPropertyName("send_by_id")]
    public SendByIdStartRequest? SendById { get; init; }

    [JsonPropertyName("send_by_numbers")]
    public SendByNumbersStartRequest? SendByNumbers { get; init; }

    [JsonPropertyName("start_at")]
    public DateTimeOffset StartAt { get; init; }

    [JsonPropertyName("repeat_interval_hours")]
    public double? RepeatIntervalHours { get; init; }

    [JsonPropertyName("max_occurrences")]
    public int? MaxOccurrences { get; init; }
}

public sealed class ScheduledCampaignDto
{
    [JsonPropertyName("id")]
    public int Id { get; init; }

    [JsonPropertyName("name")]
    public string Name { get; init; } = "";

    [JsonPropertyName("campaign_type")]
    public string CampaignType { get; init; } = "";

    [JsonPropertyName("start_at")]
    public DateTimeOffset StartAt { get; init; }

    [JsonPropertyName("repeat_interval_hours")]
    public double? RepeatIntervalHours { get; init; }

    [JsonPropertyName("max_occurrences")]
    public int? MaxOccurrences { get; init; }

    [JsonPropertyName("occurrences_run")]
    public int OccurrencesRun { get; init; }

    [JsonPropertyName("enabled")]
    public bool Enabled { get; init; }

    [JsonIgnore]
    public bool IsDisabled => !Enabled;

    [JsonPropertyName("next_run_at")]
    public DateTimeOffset NextRunAt { get; init; }

    [JsonPropertyName("last_run_at")]
    public DateTimeOffset? LastRunAt { get; init; }

    [JsonPropertyName("last_job_id")]
    public string? LastJobId { get; init; }

    [JsonPropertyName("last_error")]
    public string? LastError { get; init; }
}

public sealed class ScheduledCampaignDeleteResponse
{
    [JsonPropertyName("deleted")]
    public int Deleted { get; init; }
}
