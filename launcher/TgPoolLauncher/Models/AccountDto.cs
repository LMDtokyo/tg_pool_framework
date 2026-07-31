using System.Text.Json.Serialization;

namespace TgPoolLauncher.Models;

public sealed class ProxyStateDto
{
    [JsonPropertyName("is_active")]
    public bool IsActive { get; init; }

    [JsonPropertyName("latency_ms")]
    public double LatencyMs { get; init; }

    [JsonPropertyName("proxy_type")]
    public string ProxyType { get; init; } = "";

    [JsonPropertyName("error_message")]
    public string? ErrorMessage { get; init; }
}

public sealed class AccountDto
{
    [JsonPropertyName("phone")]
    public string Phone { get; init; } = "";

    [JsonPropertyName("session_path")]
    public string SessionPath { get; init; } = "";

    [JsonPropertyName("status")]
    public string Status { get; init; } = "unknown";

    [JsonPropertyName("is_premium")]
    public bool IsPremium { get; init; }

    [JsonPropertyName("has_2fa")]
    public bool Has2Fa { get; init; }

    [JsonPropertyName("country")]
    public string? Country { get; init; }

    [JsonPropertyName("username")]
    public string Username { get; init; } = "";

    [JsonPropertyName("first_name")]
    public string FirstName { get; init; } = "";

    [JsonPropertyName("error_message")]
    public string? ErrorMessage { get; init; }

    [JsonPropertyName("restriction_expires")]
    public DateTimeOffset? RestrictionExpires { get; init; }

    [JsonPropertyName("role")]
    public string Role { get; init; } = "";

    [JsonPropertyName("folder")]
    public string Folder { get; init; } = "";

    [JsonPropertyName("first_seen")]
    public DateTimeOffset? FirstSeen { get; init; }

    [JsonPropertyName("last_checked")]
    public DateTimeOffset? LastChecked { get; init; }

    [JsonPropertyName("uses_proxy")]
    public bool UsesProxy { get; init; }

    [JsonPropertyName("proxy_label")]
    public string? ProxyLabel { get; init; }

    [JsonPropertyName("proxy_status")]
    public string? ProxyStatus { get; init; }

    [JsonPropertyName("proxy")]
    public ProxyStateDto? Proxy { get; init; }

    [JsonPropertyName("telegram_id")]
    public string TelegramId { get; init; } = "";

    [JsonPropertyName("joined_groups")]
    public List<string> JoinedGroups { get; init; } = [];

    [JsonPropertyName("groups")]
    public List<string> Groups { get; init; } = [];
}

public sealed class AssignValueRequest
{
    [JsonPropertyName("value")]
    public string Value { get; init; } = "";
}

public sealed class RecheckRequest
{
    [JsonPropertyName("phones")]
    public List<string>? Phones { get; init; }

    [JsonPropertyName("deep")]
    public bool Deep { get; init; }
}

public sealed class RecheckResponse
{
    [JsonPropertyName("checked")]
    public int Checked { get; init; }

    [JsonPropertyName("alive")]
    public int Alive { get; init; }

    [JsonPropertyName("banned")]
    public int Banned { get; init; }

    [JsonPropertyName("unauthorized")]
    public int Unauthorized { get; init; }

    [JsonPropertyName("spamblock")]
    public int Spamblock { get; init; }

    [JsonPropertyName("frozen")]
    public int Frozen { get; init; }

    [JsonPropertyName("flood")]
    public int Flood { get; init; }
}

public sealed class RescanResponse
{
    [JsonPropertyName("new_accounts")]
    public int NewAccounts { get; init; }

    [JsonPropertyName("new_phones")]
    public List<string> NewPhones { get; init; } = [];

    [JsonPropertyName("failures")]
    public List<AccountLoadFailureDto> Failures { get; init; } = [];
}

public sealed class AccountLoadFailureDto
{
    [JsonPropertyName("file")]
    public string File { get; init; } = "";

    [JsonPropertyName("reason")]
    public string Reason { get; init; } = "";
}

public sealed class DefaultCredentialsDto
{
    [JsonPropertyName("api_id")]
    public int ApiId { get; init; }

    [JsonPropertyName("api_hash")]
    public string ApiHash { get; init; } = "";
}
