using System.Globalization;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using CommunityToolkit.Mvvm.ComponentModel;

namespace TgPoolLauncher.Models;

public class DatamollCredentialsRequest
{
    [JsonPropertyName("api_key")]
    public string ApiKey { get; init; } = "";

    [JsonPropertyName("api_secret")]
    public string ApiSecret { get; init; } = "";
}

public sealed class DatamollBalanceDto
{
    [JsonPropertyName("balance")]
    public string Balance { get; init; } = "0";

    [JsonPropertyName("credit_limit")]
    public string CreditLimit { get; init; } = "0";

    [JsonPropertyName("available_balance")]
    public string AvailableBalance { get; init; } = "0";

    [JsonPropertyName("currency")]
    public string Currency { get; init; } = "USD";
}

public sealed class DatamollCatalogDto
{
    [JsonPropertyName("items")]
    public List<DatamollProductDto> Items { get; init; } = [];
}

public sealed class DatamollProductDto
{
    private static readonly Regex CountryPattern = new(
        @"Registration country\s*:\s*(?<value>[^.|]+)",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    private static readonly Regex AgePattern = new(
        @"(?:Account age|Age)\s*:\s*(?<value>[^.|]+)",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    private static readonly Regex ParenthesizedValuePattern = new(
        @"\((?<value>[^()]+)\)\s*$",
        RegexOptions.CultureInvariant);

    [JsonPropertyName("product_id")]
    public int ProductId { get; init; }

    [JsonPropertyName("name")]
    public string Name { get; init; } = "";

    [JsonPropertyName("price")]
    public string Price { get; init; } = "0";

    [JsonPropertyName("currency")]
    public string Currency { get; init; } = "USD";

    [JsonPropertyName("stock")]
    public int Stock { get; init; }

    [JsonPropertyName("min_order")]
    public int MinOrder { get; init; } = 1;

    [JsonPropertyName("max_order")]
    public int? MaxOrder { get; init; }

    [JsonPropertyName("category_name")]
    public string? CategoryName { get; init; }

    [JsonPropertyName("description")]
    public string? Description { get; init; }

    [JsonPropertyName("country")]
    public string? Country { get; init; }

    [JsonPropertyName("content_language")]
    public string ContentLanguage { get; init; } = "";

    [JsonIgnore]
    public decimal UnitPrice =>
        decimal.TryParse(Price, NumberStyles.Number, CultureInfo.InvariantCulture, out var value)
            ? value
            : 0m;

    [JsonIgnore]
    public string CountryName
    {
        get
        {
            var descriptionCountry = ExtractDescriptionValue(CountryPattern);
            if (!string.IsNullOrWhiteSpace(descriptionCountry))
            {
                var parenthesized = ParenthesizedValuePattern.Match(descriptionCountry);
                return parenthesized.Success
                    ? parenthesized.Groups["value"].Value.Trim()
                    : descriptionCountry;
            }

            if (!string.IsNullOrWhiteSpace(Country))
            {
                try
                {
                    return new RegionInfo(Country.Trim().ToUpperInvariant()).EnglishName;
                }
                catch (ArgumentException)
                {
                    return Country.Trim().ToUpperInvariant();
                }
            }

            return "Not specified";
        }
    }

    [JsonIgnore]
    public string AccountAge
    {
        get
        {
            var value = ExtractDescriptionValue(AgePattern);
            return string.IsNullOrWhiteSpace(value) ? "Not specified" : value;
        }
    }

    [JsonIgnore]
    public string PriceDisplay => $"{Currency} {Price}";

    [JsonIgnore]
    public string AvailableDisplay => Stock.ToString("N0", CultureInfo.InvariantCulture);

    [JsonIgnore]
    public string OrderRangeDisplay =>
        MaxOrder is null ? $"{MinOrder}+" : $"{MinOrder}-{MaxOrder}";

    private string ExtractDescriptionValue(Regex pattern)
    {
        if (string.IsNullOrWhiteSpace(Description))
            return "";
        var match = pattern.Match(Description);
        return match.Success ? match.Groups["value"].Value.Trim() : "";
    }
}

public sealed class DatamollPurchaseRequest : DatamollCredentialsRequest
{
    [JsonPropertyName("product_id")]
    public int ProductId { get; init; }

    [JsonPropertyName("quantity")]
    public int Quantity { get; init; }

    [JsonPropertyName("external_order_id")]
    public string ExternalOrderId { get; init; } = "";
}

public sealed class DatamollPurchaseDto
{
    [JsonPropertyName("order_id")]
    public int OrderId { get; init; }

    [JsonPropertyName("external_order_id")]
    public string ExternalOrderId { get; init; } = "";

    [JsonPropertyName("status")]
    public string Status { get; init; } = "";

    [JsonPropertyName("payment_status")]
    public string PaymentStatus { get; init; } = "";

    [JsonPropertyName("product_id")]
    public int ProductId { get; init; }

    [JsonPropertyName("quantity")]
    public int Quantity { get; init; }

    [JsonPropertyName("unit_price")]
    public string UnitPrice { get; init; } = "0";

    [JsonPropertyName("total_amount")]
    public string TotalAmount { get; init; } = "0";

    [JsonPropertyName("currency")]
    public string Currency { get; init; } = "USD";

    [JsonPropertyName("delivered_count")]
    public int DeliveredCount { get; init; }

    [JsonPropertyName("receipt_file")]
    public string ReceiptFile { get; init; } = "";

    [JsonPropertyName("reused_existing")]
    public bool ReusedExisting { get; init; }

    [JsonPropertyName("downloaded_files")]
    public int DownloadedFiles { get; init; }

    [JsonPropertyName("imported_sessions")]
    public int ImportedSessions { get; init; }

    [JsonPropertyName("imported_tdata")]
    public int ImportedTdata { get; init; }

    [JsonPropertyName("skipped_existing")]
    public int SkippedExisting { get; init; }

    [JsonPropertyName("registered_accounts")]
    public int RegisteredAccounts { get; init; }
}

public partial class DatamollActivityRow : ObservableObject
{
    public DatamollActivityRow(
        DateTimeOffset time,
        string externalOrderId,
        string product,
        int quantity,
        string total)
    {
        Time = time;
        ExternalOrderId = externalOrderId;
        Product = product;
        Quantity = quantity;
        this.total = total;
    }

    public DateTimeOffset Time { get; }
    public string ExternalOrderId { get; }
    public string Product { get; }
    public int Quantity { get; }

    [ObservableProperty]
    private int? orderId;

    [ObservableProperty]
    private string total;

    [ObservableProperty]
    private string status = "Purchasing";

    [ObservableProperty]
    private int delivered;

    [ObservableProperty]
    private string message = "Submitting order to Datamoll...";

    public string TimeDisplay => Time.ToLocalTime().ToString("HH:mm:ss");
}
