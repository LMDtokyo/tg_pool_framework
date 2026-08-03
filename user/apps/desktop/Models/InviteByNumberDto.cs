using System.Text.Json.Serialization;

namespace TgPoolLauncher.Models;

public sealed class InviteSenderLinkRequest
{
    [JsonPropertyName("sender_phone")]
    public string SenderPhone { get; init; } = "";

    [JsonPropertyName("invite_link")]
    public string InviteLink { get; init; } = "";
}

public sealed class InviteRecipientRequest
{
    [JsonPropertyName("id")]
    public string Id { get; init; } = "";

    [JsonPropertyName("username")]
    public string? Username { get; init; }

    [JsonPropertyName("phone")]
    public string? Phone { get; init; }
}

public sealed class InviteByNumberStartRequest
{
    [JsonPropertyName("recipients")]
    public List<InviteRecipientRequest> Recipients { get; init; } = [];

    [JsonPropertyName("sender_links")]
    public List<InviteSenderLinkRequest> SenderLinks { get; init; } = [];

    [JsonPropertyName("max_per_account")]
    public int MaxPerAccount { get; init; } = 40;

    [JsonPropertyName("delay_min_sec")]
    public double DelayMinSec { get; init; } = 1;

    [JsonPropertyName("delay_max_sec")]
    public double DelayMaxSec { get; init; } = 10;

    [JsonPropertyName("max_flood_wait_sec")]
    public double MaxFloodWaitSec { get; init; } = 500;

    [JsonPropertyName("message_template")]
    public string MessageTemplate { get; init; } = "{invite_link}";

    [JsonPropertyName("require_proxy")]
    public bool RequireProxy { get; init; } = true;
}

public sealed class InviteByNumberStartResponse
{
    [JsonPropertyName("job_id")]
    public string JobId { get; init; } = "";

    [JsonPropertyName("started")]
    public bool Started { get; init; }
}

public sealed class InviteByNumberResultDto
{
    [JsonPropertyName("recipient_id")]
    public string RecipientId { get; init; } = "";

    [JsonPropertyName("sender_phone")]
    public string SenderPhone { get; init; } = "";

    [JsonPropertyName("invite_link")]
    public string InviteLink { get; init; } = "";

    [JsonPropertyName("state")]
    public string State { get; init; } = "";

    [JsonPropertyName("message")]
    public string Message { get; init; } = "";
}

public sealed class InviteByNumberStatusDto
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

    [JsonPropertyName("unproxied_senders")]
    public List<string> UnproxiedSenders { get; init; } = [];

    [JsonPropertyName("results")]
    public List<InviteByNumberResultDto> Results { get; init; } = [];
}
