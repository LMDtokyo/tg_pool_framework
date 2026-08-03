using System.Text.Json.Serialization;

namespace TgPoolLauncher.Models;

public sealed class SessionConvertItem
{
    [JsonPropertyName("session_path")]
    public string SessionPath { get; init; } = "";

    [JsonPropertyName("json_path")]
    public string JsonPath { get; init; } = "";

    [JsonPropertyName("output_subdir")]
    public string OutputSubdir { get; init; } = "";
}

public sealed class SessionConvertStartRequest
{
    [JsonPropertyName("items")]
    public List<SessionConvertItem> Items { get; init; } = new();

    [JsonPropertyName("output_base_dir")]
    public string OutputBaseDir { get; init; } = "tdata_exports";
}

public sealed class SessionConvertStartResponse
{
    [JsonPropertyName("job_id")]
    public string JobId { get; init; } = "";

    [JsonPropertyName("started")]
    public bool Started { get; init; }
}

public sealed class SessionConvertResult
{
    [JsonPropertyName("source")]
    public string Source { get; init; } = "";

    [JsonPropertyName("output")]
    public string? Output { get; init; }

    [JsonPropertyName("success")]
    public bool Success { get; init; }

    [JsonPropertyName("error")]
    public string Error { get; init; } = "";
}

public sealed class SessionConvertStatusDto
{
    [JsonPropertyName("running")]
    public bool Running { get; init; }

    [JsonPropertyName("job_id")]
    public string? JobId { get; init; }

    [JsonPropertyName("total")]
    public int Total { get; init; }

    [JsonPropertyName("results")]
    public List<SessionConvertResult> Results { get; init; } = new();

    [JsonPropertyName("finished")]
    public bool Finished { get; init; }

    [JsonPropertyName("error")]
    public string? Error { get; init; }
}
