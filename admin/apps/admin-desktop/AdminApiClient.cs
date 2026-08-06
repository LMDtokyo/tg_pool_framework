using System.Globalization;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace TgPoolAdmin.Services;

public sealed class AdminApiClient : IDisposable
{
    private const string DefaultBaseUrl = "http://127.0.0.1:8200";
    private readonly HttpClient _http;

    public AdminApiClient(Uri baseUri)
    {
        _http = new HttpClient
        {
            BaseAddress = baseUri,
            Timeout = TimeSpan.FromSeconds(45),
        };
    }

    public static Uri ResolveBaseUri()
    {
        var value = FirstConfigured(
            Environment.GetEnvironmentVariable("PAYMENT_ADMIN_URL"),
            Environment.GetEnvironmentVariable("PAYMENT_SERVER_URL"),
            DefaultBaseUrl);
        if (!Uri.TryCreate(value, UriKind.Absolute, out var uri)
            || (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
        {
            throw new InvalidOperationException(
                "PAYMENT_ADMIN_URL or PAYMENT_SERVER_URL must be an absolute HTTP/HTTPS URL.");
        }
        return new Uri(uri.AbsoluteUri.TrimEnd('/') + "/");
    }

    public async Task<AdminUsersResponse> GetUsersAsync(
        string adminKey,
        string? search = null,
        CancellationToken cancellationToken = default)
    {
        var path = "admin/users";
        if (!string.IsNullOrWhiteSpace(search))
            path += "?search=" + Uri.EscapeDataString(search.Trim());
        using var request = new HttpRequestMessage(HttpMethod.Get, path);
        request.Headers.Add("X-Admin-Key", adminKey);
        using var response = await _http.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, "load payment users", cancellationToken);
        return await response.Content.ReadFromJsonAsync<AdminUsersResponse>(
                   cancellationToken: cancellationToken)
               ?? new AdminUsersResponse();
    }

    public async Task<SalesStatistics> GetSalesStatisticsAsync(
        string adminKey,
        int days,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, $"admin/statistics/sales?days={days}");
        request.Headers.Add("X-Admin-Key", adminKey);
        using var response = await _http.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, "load sales statistics", cancellationToken);
        return await response.Content.ReadFromJsonAsync<SalesStatistics>(
                   cancellationToken: cancellationToken)
               ?? throw new InvalidOperationException("Payment server returned empty sales statistics.");
    }

    public async Task<DepositStatistics> GetDepositStatisticsAsync(
        string adminKey,
        int days,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, $"admin/statistics/deposits?days={days}");
        request.Headers.Add("X-Admin-Key", adminKey);
        using var response = await _http.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, "load deposit statistics", cancellationToken);
        return await response.Content.ReadFromJsonAsync<DepositStatistics>(
                   cancellationToken: cancellationToken)
               ?? throw new InvalidOperationException("Payment server returned empty deposit statistics.");
    }

    public async Task<AdminWithdrawalsResponse> GetWithdrawalsAsync(
        string adminKey,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, "admin/withdrawals?limit=200");
        request.Headers.Add("X-Admin-Key", adminKey);
        using var response = await _http.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, "load withdrawal history", cancellationToken);
        return await response.Content.ReadFromJsonAsync<AdminWithdrawalsResponse>(
                   cancellationToken: cancellationToken)
               ?? new AdminWithdrawalsResponse();
    }

    public async Task<AdminWithdrawal> RefreshWithdrawalAsync(
        int withdrawalId,
        string adminKey,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(
            HttpMethod.Post,
            $"admin/withdrawals/{withdrawalId}/refresh");
        request.Headers.Add("X-Admin-Key", adminKey);
        using var response = await _http.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, "refresh withdrawal status", cancellationToken);
        return await response.Content.ReadFromJsonAsync<AdminWithdrawal>(
                   cancellationToken: cancellationToken)
               ?? throw new InvalidOperationException("Payment server returned an empty withdrawal response.");
    }

    public async Task<AdminWithdrawal> CreateWithdrawalAsync(
        int userId,
        string adminKey,
        string actor,
        string idempotencyKey,
        string? amount,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(
            HttpMethod.Post,
            $"admin/users/{userId}/withdrawals");
        request.Headers.Add("X-Admin-Key", adminKey);
        request.Headers.Add("X-Admin-Actor", actor);
        request.Headers.Add("Idempotency-Key", idempotencyKey);
        request.Content = JsonContent.Create(new WithdrawalBody { Amount = amount });
        using var response = await _http.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, "withdraw wallet funds", cancellationToken);
        return await response.Content.ReadFromJsonAsync<AdminWithdrawal>(
                   cancellationToken: cancellationToken)
               ?? throw new InvalidOperationException("Payment server returned an empty withdrawal response.");
    }

    public async Task<RetailPricing> GetPricingAsync(
        string adminKey,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, "admin/pricing");
        request.Headers.Add("X-Admin-Key", adminKey);
        using var response = await _http.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, "load retail pricing", cancellationToken);
        return await response.Content.ReadFromJsonAsync<RetailPricing>(
                   cancellationToken: cancellationToken)
               ?? throw new InvalidOperationException("Payment server returned empty retail pricing.");
    }

    public async Task<RetailPricing> UpdatePricingAsync(
        string adminKey,
        string markupPercent,
        string markupFixed,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Put, "admin/pricing");
        request.Headers.Add("X-Admin-Key", adminKey);
        request.Content = JsonContent.Create(new RetailPricingBody
        {
            MarkupPercent = markupPercent,
            MarkupFixed = markupFixed,
        });
        using var response = await _http.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, "save retail pricing", cancellationToken);
        return await response.Content.ReadFromJsonAsync<RetailPricing>(
                   cancellationToken: cancellationToken)
               ?? throw new InvalidOperationException("Payment server returned empty retail pricing.");
    }

    public async Task<AdminCatalogResponse> GetCatalogAsync(
        string adminKey,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, "admin/catalog");
        request.Headers.Add("X-Admin-Key", adminKey);
        using var response = await _http.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, "load the account catalog", cancellationToken);
        return await response.Content.ReadFromJsonAsync<AdminCatalogResponse>(
                   cancellationToken: cancellationToken)
               ?? new AdminCatalogResponse();
    }

    public async Task<CountryPricingResponse> GetCountryPricingAsync(
        string adminKey,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, "admin/pricing/countries");
        request.Headers.Add("X-Admin-Key", adminKey);
        using var response = await _http.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, "load country markup overrides", cancellationToken);
        return await response.Content.ReadFromJsonAsync<CountryPricingResponse>(
                   cancellationToken: cancellationToken)
               ?? new CountryPricingResponse();
    }

    public async Task<CountryPricing> SaveCountryPricingAsync(
        string adminKey,
        string country,
        string markupPercent,
        string markupFixed,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(
            HttpMethod.Put,
            $"admin/pricing/countries/{Uri.EscapeDataString(country)}");
        request.Headers.Add("X-Admin-Key", adminKey);
        request.Content = JsonContent.Create(new RetailPricingBody
        {
            MarkupPercent = markupPercent,
            MarkupFixed = markupFixed,
        });
        using var response = await _http.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, "save the country markup", cancellationToken);
        return await response.Content.ReadFromJsonAsync<CountryPricing>(
                   cancellationToken: cancellationToken)
               ?? throw new InvalidOperationException("Payment server returned empty country pricing.");
    }

    public async Task DeleteCountryPricingAsync(
        string adminKey,
        string country,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(
            HttpMethod.Delete,
            $"admin/pricing/countries/{Uri.EscapeDataString(country)}");
        request.Headers.Add("X-Admin-Key", adminKey);
        using var response = await _http.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, "clear the country markup override", cancellationToken);
    }

    public async Task<ProviderBalance> GetDatamollBalanceAsync(
        string adminKey,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, "admin/datamoll-balance");
        request.Headers.Add("X-Admin-Key", adminKey);
        using var response = await _http.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, "load the Datamoll balance", cancellationToken);
        return await response.Content.ReadFromJsonAsync<ProviderBalance>(
                   cancellationToken: cancellationToken)
               ?? throw new InvalidOperationException("Payment server returned an empty balance response.");
    }

    public async Task<TreasuryWallet> GetTreasuryWalletAsync(
        string adminKey,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, "admin/treasury-wallet");
        request.Headers.Add("X-Admin-Key", adminKey);
        using var response = await _http.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, "load administrator wallet", cancellationToken);
        return await response.Content.ReadFromJsonAsync<TreasuryWallet>(
                   cancellationToken: cancellationToken)
               ?? throw new InvalidOperationException("Payment server returned an empty wallet response.");
    }

    public async Task<TreasuryWallet> UpdateTreasuryWalletAsync(
        string adminKey,
        string address,
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Put, "admin/treasury-wallet");
        request.Headers.Add("X-Admin-Key", adminKey);
        request.Content = JsonContent.Create(new TreasuryWalletBody { Address = address });
        using var response = await _http.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, "change administrator wallet", cancellationToken);
        return await response.Content.ReadFromJsonAsync<TreasuryWallet>(
                   cancellationToken: cancellationToken)
               ?? throw new InvalidOperationException("Payment server returned an empty wallet response.");
    }

    private static string FirstConfigured(params string?[] values) =>
        values.First(value => !string.IsNullOrWhiteSpace(value))!.Trim();

    private static async Task EnsureSuccessAsync(
        HttpResponseMessage response,
        string operation,
        CancellationToken cancellationToken)
    {
        if (response.IsSuccessStatusCode)
            return;
        var body = await response.Content.ReadAsStringAsync(cancellationToken);
        var detail = body;
        try
        {
            using var document = JsonDocument.Parse(body);
            if (document.RootElement.TryGetProperty("detail", out var element))
                detail = element.ValueKind == JsonValueKind.String ? element.GetString() ?? body : element.ToString();
        }
        catch (JsonException)
        {
            // Keep the raw response when the server does not return JSON.
        }
        throw new InvalidOperationException(
            $"Unable to {operation} ({(int)response.StatusCode}): {detail}");
    }

    public void Dispose() => _http.Dispose();

    private sealed class WithdrawalBody
    {
        [JsonPropertyName("amount")]
        public string? Amount { get; init; }
    }

    private sealed class RetailPricingBody
    {
        [JsonPropertyName("markup_percent")]
        public string MarkupPercent { get; init; } = "0";

        [JsonPropertyName("markup_fixed")]
        public string MarkupFixed { get; init; } = "0";
    }

    private sealed class TreasuryWalletBody
    {
        [JsonPropertyName("address")]
        public string Address { get; init; } = "";
    }
}

public sealed class TreasuryWallet
{
    [JsonPropertyName("address")] public string Address { get; init; } = "";
    [JsonPropertyName("network")] public string Network { get; init; } = "";
    [JsonPropertyName("asset")] public string Asset { get; init; } = "";
    [JsonPropertyName("on_chain_balance")] public string OnChainBalance { get; init; } = "0";
    [JsonPropertyName("trx_balance")] public string TrxBalance { get; init; } = "0";
}

public sealed class RetailPricing
{
    [JsonPropertyName("markup_percent")]
    public string MarkupPercent { get; init; } = "0";

    [JsonPropertyName("markup_fixed")]
    public string MarkupFixed { get; init; } = "0";
}

public sealed class ProviderBalance
{
    [JsonPropertyName("balance")] public string Balance { get; init; } = "0";
    [JsonPropertyName("available_balance")] public string AvailableBalance { get; init; } = "0";
    [JsonPropertyName("held_balance")] public string HeldBalance { get; init; } = "0";
    [JsonPropertyName("credit_limit")] public string CreditLimit { get; init; } = "0";
    [JsonPropertyName("currency")] public string Currency { get; init; } = "USD";
}

public sealed class CountryPricing
{
    [JsonPropertyName("country")] public string Country { get; init; } = "";
    [JsonPropertyName("markup_percent")] public string MarkupPercent { get; init; } = "0";
    [JsonPropertyName("markup_fixed")] public string MarkupFixed { get; init; } = "0";
}

public sealed class CountryPricingResponse
{
    [JsonPropertyName("items")]
    public List<CountryPricing> Items { get; init; } = [];
}

public sealed class AdminCatalogProduct
{
    [JsonPropertyName("product_id")] public int ProductId { get; init; }
    [JsonPropertyName("name")] public string Name { get; init; } = "";
    [JsonPropertyName("wholesale_price")] public string WholesalePrice { get; init; } = "0";
    [JsonPropertyName("retail_price")] public string RetailPrice { get; init; } = "0";
    [JsonPropertyName("currency")] public string Currency { get; init; } = "USD";
    [JsonPropertyName("stock")] public int Stock { get; init; }
    [JsonPropertyName("country")] public string? Country { get; init; }

    [JsonIgnore] public decimal WholesaleValue => ParseAmount(WholesalePrice);

    private static decimal ParseAmount(string? value) =>
        decimal.TryParse(value, NumberStyles.Number, CultureInfo.InvariantCulture, out var amount)
            ? amount
            : 0m;
}

public sealed class AdminCatalogResponse
{
    [JsonPropertyName("items")]
    public List<AdminCatalogProduct> Items { get; init; } = [];
}

public sealed class AdminUsersResponse
{
    [JsonPropertyName("items")]
    public List<AdminUser> Items { get; init; } = [];
}

public sealed class AdminUser
{
    [JsonPropertyName("user_id")] public int UserId { get; init; }
    [JsonPropertyName("telegram_user_id")] public string? TelegramUserId { get; init; }
    [JsonPropertyName("telegram_username")] public string? TelegramUsername { get; init; }
    [JsonPropertyName("display_name")] public string DisplayName { get; init; } = "";
    [JsonPropertyName("disabled")] public bool Disabled { get; init; }
    [JsonPropertyName("address")] public string Address { get; init; } = "";
    [JsonPropertyName("network")] public string Network { get; init; } = "";
    [JsonPropertyName("asset")] public string Asset { get; init; } = "USDT";
    [JsonPropertyName("on_chain_balance")] public string? OnChainBalance { get; init; }
    [JsonPropertyName("trx_balance")] public string? TrxBalance { get; init; }
    [JsonPropertyName("chain_error")] public string ChainError { get; init; } = "";
    [JsonPropertyName("database_balance")] public string DatabaseBalance { get; init; } = "0";
    [JsonPropertyName("currency")] public string Currency { get; init; } = "USD";
    [JsonPropertyName("total_accounts_purchased")] public int TotalAccountsPurchased { get; init; }
    [JsonPropertyName("total_amount_paid")] public string TotalAmountPaid { get; init; } = "0";

    [JsonIgnore] public string TelegramIdDisplay => TelegramUserId ?? "Not linked";
    [JsonIgnore] public string UsernameDisplay => string.IsNullOrWhiteSpace(TelegramUsername)
        ? (string.IsNullOrWhiteSpace(DisplayName) ? "No username" : DisplayName)
        : $"@{TelegramUsername.TrimStart('@')}";
    [JsonIgnore] public string OnChainBalanceDisplay => OnChainBalance is null
        ? "Unavailable"
        : $"{FormatAmount(OnChainBalance)} {Asset}";
    [JsonIgnore] public string TrxBalanceDisplay => TrxBalance is null
        ? "Unavailable"
        : $"{FormatAmount(TrxBalance)} TRX";
    [JsonIgnore] public string DatabaseBalanceDisplay => $"{FormatAmount(DatabaseBalance)} {Currency}";
    [JsonIgnore] public string TotalPaidDisplay => $"{FormatAmount(TotalAmountPaid)} {Currency}";
    [JsonIgnore] public decimal OnChainValue => ParseAmount(OnChainBalance);
    [JsonIgnore] public decimal DatabaseValue => ParseAmount(DatabaseBalance);
    [JsonIgnore] public decimal TotalPaidValue => ParseAmount(TotalAmountPaid);

    private static decimal ParseAmount(string? value) =>
        decimal.TryParse(value, NumberStyles.Number, CultureInfo.InvariantCulture, out var amount)
            ? amount
            : 0m;

    internal static string FormatAmount(string? value) =>
        ParseAmount(value).ToString("0.##", CultureInfo.InvariantCulture);
}

public sealed class AdminWithdrawal
{
    [JsonPropertyName("id")] public int Id { get; init; }
    [JsonPropertyName("user_id")] public int UserId { get; init; }
    [JsonPropertyName("source_address")] public string SourceAddress { get; init; } = "";
    [JsonPropertyName("destination_address")] public string DestinationAddress { get; init; } = "";
    [JsonPropertyName("requested_amount")] public string RequestedAmount { get; init; } = "0";
    [JsonPropertyName("transferred_amount")] public string? TransferredAmount { get; init; }
    [JsonPropertyName("asset")] public string Asset { get; init; } = "USDT";
    [JsonPropertyName("network")] public string Network { get; init; } = "";
    [JsonPropertyName("status")] public string Status { get; init; } = "";
    [JsonPropertyName("transaction_hash")] public string? TransactionHash { get; init; }
    [JsonPropertyName("chain_balance_before")] public string? ChainBalanceBefore { get; init; }
    [JsonPropertyName("chain_balance_after")] public string? ChainBalanceAfter { get; init; }
    [JsonPropertyName("network_fee")] public string? NetworkFee { get; init; }
    [JsonPropertyName("requested_by")] public string RequestedBy { get; init; } = "";
    [JsonPropertyName("error_message")] public string ErrorMessage { get; init; } = "";
    [JsonPropertyName("created_at")] public DateTimeOffset CreatedAt { get; init; }
    [JsonPropertyName("updated_at")] public DateTimeOffset UpdatedAt { get; init; }

    [JsonIgnore] public string AmountDisplay =>
        $"{AdminUser.FormatAmount(TransferredAmount ?? RequestedAmount)} {Asset}";
    [JsonIgnore] public string FeeDisplay => string.IsNullOrWhiteSpace(NetworkFee)
        ? "—"
        : AdminUser.FormatAmount(NetworkFee);
    [JsonIgnore] public string CreatedDisplay => CreatedAt.ToLocalTime().ToString("g");
    [JsonIgnore] public bool CanRefresh =>
        Status is "created" or "submitted" or "review_required";
}

public sealed class AdminWithdrawalsResponse
{
    [JsonPropertyName("items")]
    public List<AdminWithdrawal> Items { get; init; } = [];
}

public sealed class SalesStatistics
{
    [JsonPropertyName("days")] public int Days { get; init; }
    [JsonPropertyName("currency")] public string Currency { get; init; } = "USD";
    [JsonPropertyName("today")] public SalesTotal Today { get; init; } = new();
    [JsonPropertyName("period")] public SalesTotal Period { get; init; } = new();
    [JsonPropertyName("all_time")] public SalesTotal AllTime { get; init; } = new();
    [JsonPropertyName("daily")] public List<DailySales> Daily { get; init; } = [];
}

public class SalesTotal
{
    [JsonPropertyName("gross_sales")] public string GrossSales { get; init; } = "0";
    [JsonPropertyName("completed_orders")] public int CompletedOrders { get; init; }
    [JsonPropertyName("accounts_sold")] public int AccountsSold { get; init; }

    [JsonIgnore] public string GrossSalesDisplay => AdminUser.FormatAmount(GrossSales);
}

public sealed class DailySales : SalesTotal
{
    [JsonPropertyName("date")] public string Date { get; init; } = "";
}

public sealed class DepositStatistics
{
    [JsonPropertyName("days")] public int Days { get; init; }
    [JsonPropertyName("asset")] public string Asset { get; init; } = "USDT";
    [JsonPropertyName("today")] public DepositTotal Today { get; init; } = new();
    [JsonPropertyName("period")] public DepositTotal Period { get; init; } = new();
    [JsonPropertyName("all_time")] public DepositTotal AllTime { get; init; } = new();
    [JsonPropertyName("daily")] public List<DailyDeposit> Daily { get; init; } = [];
}

public class DepositTotal
{
    [JsonPropertyName("total_deposited")] public string TotalDeposited { get; init; } = "0";
    [JsonPropertyName("deposit_count")] public int DepositCount { get; init; }
}

public sealed class DailyDeposit : DepositTotal
{
    [JsonPropertyName("date")] public string Date { get; init; } = "";
}
