using System.Text.Json.Serialization;

namespace TgPoolLauncher.Models;

public sealed class SendByIdStartRequest
{
    [JsonPropertyName("database_path")]
    public string DatabasePath { get; init; } = "";

    [JsonPropertyName("message")]
    public string Message { get; init; } = "";

    [JsonPropertyName("sender_phones")]
    public List<string> SenderPhones { get; init; } = [];

    [JsonPropertyName("media_paths")]
    public List<string> MediaPaths { get; init; } = [];

    [JsonPropertyName("forward_links")]
    public List<string> ForwardLinks { get; init; } = [];

    [JsonPropertyName("bot_relay_username")]
    public string? BotRelayUsername { get; init; }

    [JsonPropertyName("bot_relay_message_ids")]
    public List<int> BotRelayMessageIds { get; init; } = [];

    [JsonPropertyName("sms_per_account_min")]
    public int SmsPerAccountMin { get; init; } = 1;

    [JsonPropertyName("sms_per_account_max")]
    public int SmsPerAccountMax { get; init; } = 40;

    [JsonPropertyName("delay_min_sec")]
    public double DelayMinSec { get; init; } = 1;

    [JsonPropertyName("delay_max_sec")]
    public double DelayMaxSec { get; init; } = 10;

    [JsonPropertyName("max_flood_wait_sec")]
    public double MaxFloodWaitSec { get; init; } = 500;

    [JsonPropertyName("delete_dialog")]
    public bool DeleteDialog { get; init; }

    [JsonPropertyName("link_preview")]
    public bool LinkPreview { get; init; } = true;

    [JsonPropertyName("silent")]
    public bool Silent { get; init; }

    [JsonPropertyName("auto_repost")]
    public bool AutoRepost { get; init; }

    [JsonPropertyName("leave_donor_groups")]
    public bool LeaveDonorGroups { get; init; }

    [JsonPropertyName("pin_message")]
    public bool PinMessage { get; init; }

    [JsonPropertyName("video_note")]
    public bool VideoNote { get; init; }

    [JsonPropertyName("self_destruct_sec")]
    public int? SelfDestructSec { get; init; }

    [JsonPropertyName("schedule_at")]
    public DateTimeOffset? ScheduleAt { get; init; }

    [JsonPropertyName("streams")]
    public int Streams { get; init; } = 1;

    [JsonPropertyName("auto_stop_ban")]
    public int AutoStopBan { get; init; }

    [JsonPropertyName("auto_stop_spamblock")]
    public int AutoStopSpamblock { get; init; }

    [JsonPropertyName("auto_stop_floodwait")]
    public int AutoStopFloodWait { get; init; }

    [JsonPropertyName("repeat_every_hours")]
    public double? RepeatEveryHours { get; init; }

    [JsonPropertyName("results_dir")]
    public string ResultsDir { get; init; } = "";
}

public sealed class SendByIdStartResponse
{
    [JsonPropertyName("job_id")]
    public string JobId { get; init; } = "";

    [JsonPropertyName("started")]
    public bool Started { get; init; }
}

public sealed class SendByIdResultDto
{
    [JsonPropertyName("recipient_id")]
    public long RecipientId { get; init; }

    [JsonPropertyName("sender_phone")]
    public string SenderPhone { get; init; } = "";

    [JsonPropertyName("username")]
    public string Username { get; init; } = "";

    [JsonPropertyName("donor")]
    public string Donor { get; init; } = "";

    [JsonPropertyName("state")]
    public string State { get; init; } = "";

    [JsonPropertyName("message")]
    public string Message { get; init; } = "";

    [JsonPropertyName("cycle")]
    public int Cycle { get; init; } = 1;
}

public sealed class SendByIdStatusDto
{
    [JsonPropertyName("running")]
    public bool Running { get; init; }

    [JsonPropertyName("job_id")]
    public string? JobId { get; init; }

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

    [JsonPropertyName("ban_count")]
    public int BanCount { get; init; }

    [JsonPropertyName("spamblock_count")]
    public int SpamblockCount { get; init; }

    [JsonPropertyName("floodwait_count")]
    public int FloodWaitCount { get; init; }

    [JsonPropertyName("cycle")]
    public int Cycle { get; init; } = 1;

    [JsonPropertyName("export_path")]
    public string? ExportPath { get; init; }

    [JsonPropertyName("results")]
    public List<SendByIdResultDto> Results { get; init; } = [];
}

