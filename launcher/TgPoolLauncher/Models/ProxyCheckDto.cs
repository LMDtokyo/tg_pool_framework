using System.Text.Json.Serialization;

namespace TgPoolLauncher.Models;

public sealed class ProxyCheckItem
{
    [JsonPropertyName("type")]
    public string Type { get; init; } = "socks5";

    [JsonPropertyName("host")]
    public string Host { get; init; } = "";

    [JsonPropertyName("port")]
    public int Port { get; init; }

    [JsonPropertyName("username")]
    public string? Username { get; init; }

    [JsonPropertyName("password")]
    public string? Password { get; init; }
}

public sealed class ProxyCheckStartRequest
{
    [JsonPropertyName("proxies")]
    public List<ProxyCheckItem> Proxies { get; init; } = new();

    [JsonPropertyName("concurrency")]
    public int Concurrency { get; init; } = 10;
}

public sealed class ProxyCheckStartResponse
{
    [JsonPropertyName("job_id")]
    public string JobId { get; init; } = "";

    [JsonPropertyName("started")]
    public bool Started { get; init; }
}

public sealed class ProxyCheckResult
{
    [JsonPropertyName("host")]
    public string Host { get; init; } = "";

    [JsonPropertyName("port")]
    public int Port { get; init; }

    [JsonPropertyName("proxy_type")]
    public string ProxyType { get; init; } = "";

    [JsonPropertyName("is_active")]
    public bool IsActive { get; init; }

    [JsonPropertyName("latency_ms")]
    public double LatencyMs { get; init; }

    [JsonPropertyName("error_message")]
    public string? ErrorMessage { get; init; }

    [JsonPropertyName("country")]
    public string? Country { get; init; }
}

public sealed class ProxyCheckStatusDto
{
    [JsonPropertyName("running")]
    public bool Running { get; init; }

    [JsonPropertyName("job_id")]
    public string? JobId { get; init; }

    [JsonPropertyName("total")]
    public int Total { get; init; }

    [JsonPropertyName("results")]
    public List<ProxyCheckResult> Results { get; init; } = new();

    [JsonPropertyName("finished")]
    public bool Finished { get; init; }

    [JsonPropertyName("error")]
    public string? Error { get; init; }
}

public sealed class StoredProxyDto
{
    [JsonPropertyName("id")]
    public int Id { get; init; }

    [JsonPropertyName("proxy_type")]
    public string ProxyType { get; init; } = "";

    [JsonPropertyName("host")]
    public string Host { get; init; } = "";

    [JsonPropertyName("port")]
    public int Port { get; init; }

    [JsonPropertyName("username")]
    public string Username { get; init; } = "";

    [JsonPropertyName("password")]
    public string Password { get; init; } = "";

    [JsonPropertyName("version")]
    public string Version { get; init; } = "ipv4";

    [JsonPropertyName("status")]
    public string Status { get; init; } = "unknown";

    [JsonPropertyName("response_ms")]
    public double? ResponseMs { get; init; }

    [JsonPropertyName("country")]
    public string? Country { get; init; }

    [JsonPropertyName("error_message")]
    public string? ErrorMessage { get; init; }

    [JsonPropertyName("last_checked_at")]
    public DateTimeOffset? LastCheckedAt { get; init; }
}

public sealed class ProxyBulkCreateRequest
{
    [JsonPropertyName("protocol")]
    public string Protocol { get; init; } = "http";

    [JsonPropertyName("proxy_list")]
    public string ProxyList { get; init; } = "";
}

public sealed class StoredProxyCheckRequest
{
    [JsonPropertyName("proxy_ids")]
    public List<int>? ProxyIds { get; init; }

    [JsonPropertyName("concurrency")]
    public int Concurrency { get; init; } = 10;

    [JsonPropertyName("timeout")]
    public double Timeout { get; init; } = 10;

    [JsonPropertyName("retries")]
    public int Retries { get; init; } = 2;

    [JsonPropertyName("retry_delay")]
    public double RetryDelay { get; init; } = 0.5;
}

public sealed class StoredProxyCheckStatusDto
{
    [JsonPropertyName("running")]
    public bool Running { get; init; }

    [JsonPropertyName("job_id")]
    public string? JobId { get; init; }

    [JsonPropertyName("total")]
    public int Total { get; init; }

    [JsonPropertyName("completed")]
    public int Completed { get; init; }

    [JsonPropertyName("finished")]
    public bool Finished { get; init; }

    [JsonPropertyName("error")]
    public string? Error { get; init; }
}

public sealed class ProxyDeleteResponse
{
    [JsonPropertyName("deleted")]
    public int Deleted { get; init; }
}

public sealed class ProxyPoolCheckStartRequest
{
    [JsonPropertyName("mode")]
    public string Mode { get; init; } = "rotating";

    [JsonPropertyName("protocol")]
    public string Protocol { get; init; } = "http";

    [JsonPropertyName("proxies")]
    public List<ProxyCheckItem> Proxies { get; init; } = new();

    [JsonPropertyName("request_count")]
    public int? RequestCount { get; init; }

    [JsonPropertyName("concurrency")]
    public int Concurrency { get; init; } = 10;
}

public sealed class ProxyPoolCheckStartResponse
{
    [JsonPropertyName("job_id")]
    public string JobId { get; init; } = "";

    [JsonPropertyName("started")]
    public bool Started { get; init; }
}

public sealed class ProxyPoolCheckStatusDto
{
    [JsonPropertyName("running")]
    public bool Running { get; init; }

    [JsonPropertyName("job_id")]
    public string? JobId { get; init; }

    [JsonPropertyName("mode")]
    public string Mode { get; init; } = "";

    [JsonPropertyName("total")]
    public int Total { get; init; }

    [JsonPropertyName("unique")]
    public int Unique { get; init; }

    [JsonPropertyName("duplicates")]
    public int Duplicates { get; init; }

    [JsonPropertyName("connection_errors")]
    public int ConnectionErrors { get; init; }

    [JsonPropertyName("finished")]
    public bool Finished { get; init; }

    [JsonPropertyName("error")]
    public string? Error { get; init; }
}
