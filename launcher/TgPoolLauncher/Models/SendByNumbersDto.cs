using System.Text.Json.Serialization;

namespace TgPoolLauncher.Models;

public sealed class SendByNumbersStartRequest
{
    [JsonPropertyName("phone_numbers")]
    public List<string> PhoneNumbers { get; init; } = [];

    [JsonPropertyName("message")]
    public string Message { get; init; } = "";

    [JsonPropertyName("sender_phones")]
    public List<string> SenderPhones { get; init; } = [];

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

    [JsonPropertyName("link_preview")]
    public bool LinkPreview { get; init; } = true;

    [JsonPropertyName("silent")]
    public bool Silent { get; init; }

    [JsonPropertyName("delete_dialog")]
    public bool DeleteDialog { get; init; }

    [JsonPropertyName("request_profile")]
    public bool RequestProfile { get; init; }

    [JsonPropertyName("pin_message")]
    public bool PinMessage { get; init; }

    [JsonPropertyName("use_base_data")]
    public bool UseBaseData { get; init; }

    [JsonPropertyName("auto_repost")]
    public bool AutoRepost { get; init; }

    [JsonPropertyName("video_note")]
    public bool VideoNote { get; init; }

    [JsonPropertyName("self_destruct_sec")]
    public int? SelfDestructSec { get; init; }

    [JsonPropertyName("sending_by_time")]
    public bool SendingByTime { get; init; }

    [JsonPropertyName("streams_control")]
    public bool StreamsControl { get; init; }

    [JsonPropertyName("auto_stop")]
    public bool AutoStop { get; init; }
}

public sealed class SendByNumbersStartResponse
{
    [JsonPropertyName("job_id")]
    public string JobId { get; init; } = "";

    [JsonPropertyName("started")]
    public bool Started { get; init; }
}

public sealed class SendByNumbersResultDto
{
    [JsonPropertyName("recipient_phone")]
    public string RecipientPhone { get; init; } = "";

    [JsonPropertyName("sender_phone")]
    public string SenderPhone { get; init; } = "";

    [JsonPropertyName("state")]
    public string State { get; init; } = "";

    [JsonPropertyName("message")]
    public string Message { get; init; } = "";

    [JsonPropertyName("first_name")]
    public string FirstName { get; init; } = "";

    [JsonPropertyName("last_name")]
    public string LastName { get; init; } = "";

    [JsonPropertyName("bio")]
    public string Bio { get; init; } = "";
}

public sealed class SendByNumbersStatusDto
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

    [JsonPropertyName("results")]
    public List<SendByNumbersResultDto> Results { get; init; } = [];
}
