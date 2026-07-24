using System.Text.Json.Serialization;

namespace TgPoolLauncher.Models;

public class HeroSmsApiKeyRequest
{
    [JsonPropertyName("api_key")]
    public string ApiKey { get; init; } = "";
}

public sealed class HeroSmsBalanceDto
{
    [JsonPropertyName("balance")]
    public decimal Balance { get; init; }
}

public sealed class HeroSmsOperatorsRequest : HeroSmsApiKeyRequest
{
    [JsonPropertyName("country_id")]
    public int CountryId { get; init; }
}

public sealed class HeroSmsOperatorsDto
{
    [JsonPropertyName("operators")]
    public List<string> Operators { get; init; } = [];
}

public sealed class HeroSmsPriceRequest : HeroSmsApiKeyRequest
{
    [JsonPropertyName("country_id")]
    public int CountryId { get; init; }
}

public sealed class HeroSmsPriceDto
{
    [JsonPropertyName("price")]
    public decimal? Price { get; init; }

    [JsonPropertyName("available")]
    public int Available { get; init; }

    [JsonPropertyName("offers")]
    public List<HeroSmsPriceOfferDto> Offers { get; init; } = [];
}

public sealed class HeroSmsPriceOfferDto
{
    [JsonPropertyName("price")]
    public decimal Price { get; init; }

    [JsonPropertyName("available")]
    public int Available { get; init; }
}

public sealed class HeroSmsActivationStartRequest : HeroSmsApiKeyRequest
{
    [JsonPropertyName("country_id")]
    public int CountryId { get; init; }

    [JsonPropertyName("operator")]
    public string Operator { get; init; } = "any";

    [JsonPropertyName("target_count")]
    public int TargetCount { get; init; }

    [JsonPropertyName("concurrency")]
    public int Concurrency { get; init; }

    [JsonPropertyName("timeout_sec")]
    public int TimeoutSec { get; init; }

    [JsonPropertyName("max_price")]
    public decimal MaxPrice { get; init; }

    [JsonPropertyName("price_ceiling")]
    public decimal? PriceCeiling { get; init; }

    [JsonPropertyName("price_offers")]
    public List<decimal> PriceOffers { get; init; } = [];
}

public sealed class HeroSmsActivationStartResponse
{
    [JsonPropertyName("job_id")]
    public string JobId { get; init; } = "";

    [JsonPropertyName("started")]
    public bool Started { get; init; }
}

public sealed class HeroSmsActivationRowDto
{
    [JsonPropertyName("started_at")]
    public DateTimeOffset StartedAt { get; init; }

    [JsonPropertyName("remaining_timeout_sec")]
    public int RemainingTimeoutSec { get; init; }

    [JsonIgnore]
    public string TimeDisplay
    {
        get
        {
            var seconds = Math.Max(0, RemainingTimeoutSec);
            return $"{seconds / 60:00}:{seconds % 60:00}";
        }
    }

    [JsonPropertyName("row_id")]
    public string RowId { get; init; } = "";

    [JsonPropertyName("activation_id")]
    public string ActivationId { get; init; } = "";

    [JsonPropertyName("phone_number")]
    public string PhoneNumber { get; init; } = "";

    [JsonPropertyName("operator")]
    public string Operator { get; init; } = "";

    [JsonPropertyName("cost")]
    public decimal Cost { get; init; }

    [JsonPropertyName("status")]
    public string Status { get; init; } = "";

    [JsonPropertyName("stage")]
    public string Stage { get; init; } = "";

    [JsonPropertyName("code")]
    public string Code { get; init; } = "";

    [JsonPropertyName("message")]
    public string Message { get; init; } = "";

    [JsonPropertyName("needs_2fa")]
    public bool NeedsTwoFactor { get; init; }

    [JsonPropertyName("session_file")]
    public string SessionFile { get; init; } = "";

    [JsonPropertyName("created_new_account")]
    public bool CreatedNewAccount { get; init; }
}

public sealed class HeroSmsTwoFactorRequest
{
    [JsonPropertyName("password")]
    public string Password { get; init; } = "";
}

public sealed class HeroSmsActivationStatusDto
{
    [JsonPropertyName("running")]
    public bool Running { get; init; }

    [JsonPropertyName("job_id")]
    public string? JobId { get; init; }

    [JsonPropertyName("rows")]
    public List<HeroSmsActivationRowDto> Rows { get; init; } = [];

    [JsonPropertyName("error")]
    public string? Error { get; init; }

    [JsonPropertyName("target_count")]
    public int TargetCount { get; init; }

    [JsonPropertyName("success_count")]
    public int SuccessCount { get; init; }

    [JsonPropertyName("concurrency")]
    public int Concurrency { get; init; }

    [JsonPropertyName("active_count")]
    public int ActiveCount { get; init; }
}

public sealed class HeroSmsCountryDto
{
    [JsonPropertyName("id")]
    public int Id { get; init; }

    [JsonPropertyName("rus")]
    public string RussianName { get; init; } = "";

    [JsonPropertyName("eng")]
    public string EnglishName { get; init; } = "";

    [JsonPropertyName("chn")]
    public string ChineseName { get; init; } = "";

    [JsonPropertyName("visible")]
    public int Visible { get; init; }

    [JsonPropertyName("retry")]
    public int Retry { get; init; }
}

public sealed record HeroSmsCountryOption(int Id, string DisplayName, bool IsPlaceholder = false)
{
    public override string ToString() => DisplayName;
}

public sealed record HeroSmsOperatorOption(string Value, string DisplayName, bool IsPlaceholder = false)
{
    public override string ToString() => DisplayName;
}

public sealed record HeroSmsPriceOption(decimal Price, int Available, string DisplayName)
{
    public override string ToString() => DisplayName;
}
