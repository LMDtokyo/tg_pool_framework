using System.Text.Json.Serialization;

namespace TgPoolLauncher.Models;

public sealed class TdataConvertStartRequest
{
    [JsonPropertyName("tdata_dir")]
    public string TdataDir { get; init; } = "";

    [JsonPropertyName("output_dir")]
    public string OutputDir { get; init; } = "sessions";

    [JsonPropertyName("all_accounts")]
    public bool AllAccounts { get; init; }

    [JsonPropertyName("passwords")]
    public Dictionary<string, string>? Passwords { get; init; }
}

public sealed class TdataConvertStartResponse
{
    [JsonPropertyName("job_id")]
    public string JobId { get; init; } = "";

    [JsonPropertyName("started")]
    public bool Started { get; init; }
}

public sealed class TdataConvertResult
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

public sealed class TdataConvertStatusDto
{
    [JsonPropertyName("running")]
    public bool Running { get; init; }

    [JsonPropertyName("job_id")]
    public string? JobId { get; init; }

    [JsonPropertyName("total")]
    public int Total { get; init; }

    [JsonPropertyName("results")]
    public List<TdataConvertResult> Results { get; init; } = new();

    [JsonPropertyName("finished")]
    public bool Finished { get; init; }

    [JsonPropertyName("error")]
    public string? Error { get; init; }
}
