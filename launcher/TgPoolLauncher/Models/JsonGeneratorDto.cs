using System.Text.Json.Serialization;

namespace TgPoolLauncher.Models;

public sealed class JsonGeneratorStartRequest
{
    [JsonPropertyName("database_path")]
    public string DatabasePath { get; init; } = "";

    [JsonPropertyName("sessions_dir")]
    public string SessionsDir { get; init; } = "";

    [JsonPropertyName("output_dir")]
    public string OutputDir { get; init; } = "";
}

public sealed class JsonGeneratorStartResponse
{
    [JsonPropertyName("job_id")]
    public string JobId { get; init; } = "";

    [JsonPropertyName("started")]
    public bool Started { get; init; }
}

public sealed class JsonGeneratorResult
{
    [JsonPropertyName("time")]
    public string Time { get; init; } = "";

    [JsonPropertyName("account")]
    public string Account { get; init; } = "";

    [JsonPropertyName("message")]
    public string Message { get; init; } = "";

    [JsonPropertyName("success")]
    public bool Success { get; init; }
}

public sealed class JsonGeneratorStatusDto
{
    [JsonPropertyName("running")]
    public bool Running { get; init; }

    [JsonPropertyName("job_id")]
    public string? JobId { get; init; }

    [JsonPropertyName("total")]
    public int Total { get; init; }

    [JsonPropertyName("results")]
    public List<JsonGeneratorResult> Results { get; init; } = new();

    [JsonPropertyName("finished")]
    public bool Finished { get; init; }

    [JsonPropertyName("cancelled")]
    public bool Cancelled { get; init; }

    [JsonPropertyName("error")]
    public string? Error { get; init; }
}
