using System.Text.Json.Serialization;

namespace TgPoolLauncher.Models;

public sealed class StoriesStartRequest
{
    [JsonPropertyName("action_type")]
    public string ActionType { get; init; } = "";

    [JsonPropertyName("target_chat")]
    public string TargetChat { get; init; } = "";

    [JsonPropertyName("target_story_id")]
    public int TargetStoryId { get; init; }

    [JsonPropertyName("reaction_emoji")]
    public string ReactionEmoji { get; init; } = "";

    [JsonPropertyName("media_path")]
    public string MediaPath { get; init; } = "";

    [JsonPropertyName("caption")]
    public string Caption { get; init; } = "";

    [JsonPropertyName("privacy")]
    public string Privacy { get; init; } = "everyone";

    [JsonPropertyName("period_hours")]
    public int? PeriodHours { get; init; }

    [JsonPropertyName("sender_phones")]
    public List<string> SenderPhones { get; init; } = [];

    [JsonPropertyName("streams")]
    public int Streams { get; init; } = 1;

    [JsonPropertyName("delay_min_sec")]
    public double DelayMinSec { get; init; } = 1;

    [JsonPropertyName("delay_max_sec")]
    public double DelayMaxSec { get; init; } = 8;

    [JsonPropertyName("max_flood_wait_sec")]
    public double MaxFloodWaitSec { get; init; } = 120;

    [JsonPropertyName("daily_cap_per_account")]
    public int? DailyCapPerAccount { get; init; }

    [JsonPropertyName("max_total_accounts")]
    public int? MaxTotalAccounts { get; init; }

    [JsonPropertyName("auto_stop_ban")]
    public int AutoStopBan { get; init; }

    [JsonPropertyName("auto_stop_spamblock")]
    public int AutoStopSpamblock { get; init; }

    [JsonPropertyName("auto_stop_floodwait")]
    public int AutoStopFloodWait { get; init; }

    [JsonPropertyName("require_proxy")]
    public bool RequireProxy { get; init; }

    [JsonPropertyName("results_dir")]
    public string ResultsDir { get; init; } = "";
}

public sealed class StoriesStartResponse
{
    [JsonPropertyName("job_id")]
    public string JobId { get; init; } = "";

    [JsonPropertyName("started")]
    public bool Started { get; init; }
}

public sealed class StoriesResultDto
{
    [JsonPropertyName("account_phone")]
    public string AccountPhone { get; init; } = "";

    [JsonPropertyName("state")]
    public string State { get; init; } = "";

    [JsonPropertyName("message")]
    public string Message { get; init; } = "";
}

public sealed class StoriesStatusDto
{
    [JsonPropertyName("running")]
    public bool Running { get; init; }

    [JsonPropertyName("job_id")]
    public string? JobId { get; init; }

    [JsonPropertyName("action_type")]
    public string? ActionType { get; init; }

    [JsonPropertyName("total")]
    public int Total { get; init; }

    [JsonPropertyName("succeeded")]
    public int Succeeded { get; init; }

    [JsonPropertyName("failed")]
    public int Failed { get; init; }

    [JsonPropertyName("skipped_daily_cap")]
    public int SkippedDailyCap { get; init; }

    [JsonPropertyName("finished")]
    public bool Finished { get; init; }

    [JsonPropertyName("error")]
    public string? Error { get; init; }

    [JsonPropertyName("ban_count")]
    public int BanCount { get; init; }

    [JsonPropertyName("spamblock_count")]
    public int SpamblockCount { get; init; }

    [JsonPropertyName("floodwait_count")]
    public int FloodWaitCount { get; init; }

    [JsonPropertyName("export_path")]
    public string? ExportPath { get; init; }

    [JsonPropertyName("results")]
    public List<StoriesResultDto> Results { get; init; } = [];
}
