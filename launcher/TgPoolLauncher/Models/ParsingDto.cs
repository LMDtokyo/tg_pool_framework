using System.Text.Json.Serialization;

namespace TgPoolLauncher.Models;

public sealed class ParseFilterIn
{
    [JsonPropertyName("last_seen_days")]
    public int? LastSeenDays { get; init; }

    [JsonPropertyName("gender")]
    public string? Gender { get; init; }

    [JsonPropertyName("has_avatar")]
    public bool HasAvatar { get; init; }

    [JsonPropertyName("premium")]
    public bool Premium { get; init; }

    [JsonPropertyName("exclude_bots")]
    public bool ExcludeBots { get; init; } = true;
}

public sealed class ParseStartRequest
{
    [JsonPropertyName("entities")]
    public List<string> Entities { get; init; } = new();

    [JsonPropertyName("strategy")]
    public string Strategy { get; init; } = "members";

    [JsonPropertyName("topic_id")]
    public int? TopicId { get; init; }

    [JsonPropertyName("filters")]
    public ParseFilterIn Filters { get; init; } = new();

    [JsonPropertyName("export_mode")]
    public string ExportMode { get; init; } = "full";

    [JsonPropertyName("export_path")]
    public string? ExportPath { get; init; }

    [JsonPropertyName("language")]
    public string Language { get; init; } = "ru";
}

public sealed class ParseStartResponse
{
    [JsonPropertyName("job_id")]
    public string JobId { get; init; } = "";

    [JsonPropertyName("started")]
    public bool Started { get; init; }
}

public sealed class ParseStatusDto
{
    [JsonPropertyName("running")]
    public bool Running { get; init; }

    [JsonPropertyName("job_id")]
    public string? JobId { get; init; }

    [JsonPropertyName("entities")]
    public List<string> Entities { get; init; } = new();

    [JsonPropertyName("total_collected")]
    public int TotalCollected { get; init; }

    [JsonPropertyName("sources")]
    public List<string> Sources { get; init; } = new();

    [JsonPropertyName("export_path")]
    public string? ExportPath { get; init; }

    [JsonPropertyName("db_path")]
    public string? DbPath { get; init; }

    [JsonPropertyName("report_path")]
    public string? ReportPath { get; init; }

    [JsonPropertyName("txt_path")]
    public string? TxtPath { get; init; }

    [JsonPropertyName("accounts_used")]
    public int AccountsUsed { get; init; }

    [JsonPropertyName("stats")]
    public Dictionary<string, int>? Stats { get; init; }

    [JsonPropertyName("finished")]
    public bool Finished { get; init; }

    [JsonPropertyName("error")]
    public string? Error { get; init; }
}

public sealed class ParseSourceOut
{
    [JsonPropertyName("identifier")]
    public string Identifier { get; init; } = "";

    [JsonPropertyName("title")]
    public string Title { get; init; } = "";

    [JsonPropertyName("kind")]
    public string Kind { get; init; } = "";

    [JsonPropertyName("members_count")]
    public int? MembersCount { get; init; }
}

public sealed class ParseSourcesResponse
{
    [JsonPropertyName("sources")]
    public List<ParseSourceOut> Sources { get; init; } = new();
}
