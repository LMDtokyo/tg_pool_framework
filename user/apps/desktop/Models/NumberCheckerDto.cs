using System.Text.Json.Serialization;

namespace TgPoolLauncher.Models;

public sealed class NumberCheckerStartRequest
{
    [JsonPropertyName("phone_numbers")]
    public List<string> PhoneNumbers { get; init; } = [];

    [JsonPropertyName("database_path")]
    public string? DatabasePath { get; init; }

    [JsonPropertyName("sender_phones")]
    public List<string> SenderPhones { get; init; } = [];

    [JsonPropertyName("request_profile_data")]
    public bool RequestProfileData { get; init; }

    [JsonPropertyName("gender_detection")]
    public bool GenderDetection { get; init; }

    [JsonPropertyName("delay_min_sec")]
    public double DelayMinSec { get; init; } = 5;

    [JsonPropertyName("delay_max_sec")]
    public double DelayMaxSec { get; init; } = 10;

    [JsonPropertyName("max_flood_wait_sec")]
    public double MaxFloodWaitSec { get; init; } = 500;

    [JsonPropertyName("requests_per_account")]
    public int RequestsPerAccount { get; init; } = 8;

    [JsonPropertyName("streams")]
    public int Streams { get; init; } = 1;

    [JsonPropertyName("stream_delay_min_sec")]
    public double StreamDelayMinSec { get; init; } = 30;

    [JsonPropertyName("stream_delay_max_sec")]
    public double StreamDelayMaxSec { get; init; } = 45;

    [JsonPropertyName("remove_imported_contacts")]
    public bool RemoveImportedContacts { get; init; } = true;

    [JsonPropertyName("results_dir")]
    public string ResultsDir { get; init; } = "";
}

public sealed class NumberCheckerStartResponse
{
    [JsonPropertyName("job_id")]
    public string JobId { get; init; } = "";

    [JsonPropertyName("started")]
    public bool Started { get; init; }
}

public sealed class NumberCheckerResultDto
{
    [JsonPropertyName("phone")]
    public string Phone { get; init; } = "";

    [JsonPropertyName("state")]
    public string State { get; init; } = "";

    [JsonPropertyName("account_phone")]
    public string AccountPhone { get; init; } = "";

    [JsonPropertyName("telegram_id")]
    public string TelegramId { get; init; } = "";

    [JsonPropertyName("username")]
    public string Username { get; init; } = "";

    [JsonPropertyName("first_name")]
    public string FirstName { get; init; } = "";

    [JsonPropertyName("last_name")]
    public string LastName { get; init; } = "";

    [JsonPropertyName("bio")]
    public string Bio { get; init; } = "";

    [JsonPropertyName("online_status")]
    public string OnlineStatus { get; init; } = "";

    [JsonPropertyName("last_seen")]
    public string LastSeen { get; init; } = "";

    [JsonPropertyName("gender")]
    public string Gender { get; init; } = "";

    [JsonPropertyName("message")]
    public string Message { get; init; } = "";
}

public sealed class NumberCheckerStatusDto
{
    [JsonPropertyName("running")]
    public bool Running { get; init; }

    [JsonPropertyName("job_id")]
    public string? JobId { get; init; }

    [JsonPropertyName("database_path")]
    public string? DatabasePath { get; init; }

    [JsonPropertyName("export_path")]
    public string? ExportPath { get; init; }

    [JsonPropertyName("total")]
    public int Total { get; init; }

    [JsonPropertyName("found")]
    public int Found { get; init; }

    [JsonPropertyName("not_found")]
    public int NotFound { get; init; }

    [JsonPropertyName("failed")]
    public int Failed { get; init; }

    [JsonPropertyName("pending")]
    public int Pending { get; init; }

    [JsonPropertyName("per_account")]
    public Dictionary<string, int> PerAccount { get; init; } = [];

    [JsonPropertyName("finished")]
    public bool Finished { get; init; }

    [JsonPropertyName("error")]
    public string? Error { get; init; }

    [JsonPropertyName("results")]
    public List<NumberCheckerResultDto> Results { get; init; } = [];
}
