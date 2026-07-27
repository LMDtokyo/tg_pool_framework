using System.Net.Http;
using System.Net.Http.Json;
using TgPoolLauncher.Localization;
using TgPoolLauncher.Models;

namespace TgPoolLauncher.Services;

/// <summary>
/// Typed HttpClient wrapper for the control API (src/api/app.py).
/// Registered via AddHttpClient&lt;BackendClient&gt;() in App.xaml.cs, so BaseAddress
/// is configured once there from BackendProcessManager.BaseUri.
/// </summary>
public sealed class BackendClient
{
    private readonly HttpClient _http;

    public BackendClient(HttpClient http)
    {
        _http = http;
    }

    public async Task<bool> IsHealthyAsync(CancellationToken ct = default)
    {
        try
        {
            var resp = await _http.GetAsync("/health", ct);
            return resp.IsSuccessStatusCode;
        }
        catch (HttpRequestException)
        {
            return false;
        }
    }

    /// <summary>
    /// Forwards the cached license key + hwid to the local backend so its own
    /// gate (src/api/license_gate.py) picks up the activation. Never throws
    /// on a rejection -- the returned DTO's Valid/Reason describe it instead,
    /// matching the backend's always-200 /license/activate contract.
    /// </summary>
    public async Task<LicenseStatusDto> ActivateLicenseAsync(
        string licenseKey, string hwid, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync(
            "/license/activate", new LicenseActivateRequest { LicenseKey = licenseKey, Hwid = hwid }, ct);
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadFromJsonAsync<LicenseStatusDto>(ct) ?? new LicenseStatusDto();
    }

    public async Task<List<AccountDto>> GetAccountsAsync(
        string? status = null,
        string? role = null,
        string? folder = null,
        string? country = null,
        string? text = null,
        string? sortBy = null,
        CancellationToken ct = default)
    {
        var query = new List<string>();
        void Add(string key, string? value)
        {
            if (!string.IsNullOrWhiteSpace(value))
                query.Add($"{key}={Uri.EscapeDataString(value)}");
        }
        Add("status", status);
        Add("role", role);
        Add("folder", folder);
        Add("country", country);
        Add("text", text);
        Add("sort_by", sortBy);

        var path = "/accounts" + (query.Count > 0 ? "?" + string.Join("&", query) : "");
        var result = await _http.GetFromJsonAsync<List<AccountDto>>(path, ct);
        return result ?? [];
    }

    public async Task<DatamollBalanceDto> GetDatamollBalanceAsync(
        string apiKey,
        string apiSecret,
        CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync(
            "/datamoll/balance",
            new DatamollCredentialsRequest { ApiKey = apiKey, ApiSecret = apiSecret },
            ct);
        await EnsureDatamollSuccessAsync(resp, "load the balance", ct);
        return await resp.Content.ReadFromJsonAsync<DatamollBalanceDto>(ct)
            ?? throw new InvalidOperationException("Datamoll returned an empty balance response");
    }

    public async Task<DatamollCatalogDto> GetDatamollCatalogAsync(
        string apiKey,
        string apiSecret,
        CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync(
            "/datamoll/catalog",
            new DatamollCredentialsRequest { ApiKey = apiKey, ApiSecret = apiSecret },
            ct);
        await EnsureDatamollSuccessAsync(resp, "load the Telegram catalog", ct);
        return await resp.Content.ReadFromJsonAsync<DatamollCatalogDto>(ct)
            ?? new DatamollCatalogDto();
    }

    public async Task<DatamollPurchaseDto> PurchaseDatamollAccountsAsync(
        DatamollPurchaseRequest request,
        CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/datamoll/orders", request, ct);
        await EnsureDatamollSuccessAsync(resp, "purchase the selected accounts", ct);
        return await resp.Content.ReadFromJsonAsync<DatamollPurchaseDto>(ct)
            ?? throw new InvalidOperationException("Datamoll returned an empty order response");
    }

    private static async Task EnsureDatamollSuccessAsync(
        HttpResponseMessage response,
        string operation,
        CancellationToken ct)
    {
        if (response.IsSuccessStatusCode)
            return;
        var detail = await response.Content.ReadAsStringAsync(ct);
        throw new InvalidOperationException(
            $"Unable to {operation} ({(int)response.StatusCode}): {detail}");
    }

    public async Task<List<HeroSmsCountryDto>> GetHeroSmsCountriesAsync(
        string apiKey, CancellationToken ct = default) =>
        await GetSmsProviderCountriesAsync("hero_sms", "Hero SMS", apiKey, ct);

    public async Task<List<HeroSmsCountryDto>> GetSmsPoolCountriesAsync(
        string apiKey, CancellationToken ct = default) =>
        await GetSmsProviderCountriesAsync("sms_pool", "SMSpool", apiKey, ct);

    public async Task<List<HeroSmsCountryDto>> GetGrizzlySmsCountriesAsync(
        string apiKey, CancellationToken ct = default) =>
        await GetSmsProviderCountriesAsync("grizzly_sms", "GrizzlySMS", apiKey, ct);

    private async Task<List<HeroSmsCountryDto>> GetSmsProviderCountriesAsync(
        string providerPath, string providerName, string apiKey, CancellationToken ct)
    {
        var resp = await _http.PostAsJsonAsync(
            $"/{providerPath}/countries", new HeroSmsApiKeyRequest { ApiKey = apiKey }, ct);
        if (!resp.IsSuccessStatusCode)
        {
            var detail = await resp.Content.ReadAsStringAsync(ct);
            throw new InvalidOperationException(
                $"Unable to load {providerName} countries ({(int)resp.StatusCode}): {detail}");
        }

        return await resp.Content.ReadFromJsonAsync<List<HeroSmsCountryDto>>(ct) ?? [];
    }

    public async Task<HeroSmsBalanceDto> GetHeroSmsBalanceAsync(
        string apiKey, CancellationToken ct = default) =>
        await GetSmsProviderBalanceAsync("hero_sms", "Hero SMS", apiKey, ct);

    public async Task<HeroSmsBalanceDto> GetSmsPoolBalanceAsync(
        string apiKey, CancellationToken ct = default) =>
        await GetSmsProviderBalanceAsync("sms_pool", "SMSpool", apiKey, ct);

    public async Task<HeroSmsBalanceDto> GetGrizzlySmsBalanceAsync(
        string apiKey, CancellationToken ct = default) =>
        await GetSmsProviderBalanceAsync("grizzly_sms", "GrizzlySMS", apiKey, ct);

    private async Task<HeroSmsBalanceDto> GetSmsProviderBalanceAsync(
        string providerPath, string providerName, string apiKey, CancellationToken ct)
    {
        var resp = await _http.PostAsJsonAsync(
            $"/{providerPath}/balance", new HeroSmsApiKeyRequest { ApiKey = apiKey }, ct);
        if (!resp.IsSuccessStatusCode)
        {
            var detail = await resp.Content.ReadAsStringAsync(ct);
            throw new InvalidOperationException(
                $"Unable to load {providerName} balance ({(int)resp.StatusCode}): {detail}");
        }

        return await resp.Content.ReadFromJsonAsync<HeroSmsBalanceDto>(ct)
            ?? throw new InvalidOperationException($"{providerName} returned an empty balance response");
    }

    public async Task<HeroSmsOperatorsDto> GetHeroSmsOperatorsAsync(
        string apiKey, int countryId, CancellationToken ct = default) =>
        await GetSmsProviderOperatorsAsync("hero_sms", "Hero SMS", apiKey, countryId, ct);

    public async Task<HeroSmsOperatorsDto> GetSmsPoolOperatorsAsync(
        string apiKey, int countryId, CancellationToken ct = default) =>
        await GetSmsProviderOperatorsAsync("sms_pool", "SMSpool", apiKey, countryId, ct);

    public async Task<HeroSmsOperatorsDto> GetGrizzlySmsOperatorsAsync(
        string apiKey, int countryId, CancellationToken ct = default) =>
        await GetSmsProviderOperatorsAsync("grizzly_sms", "GrizzlySMS", apiKey, countryId, ct);

    private async Task<HeroSmsOperatorsDto> GetSmsProviderOperatorsAsync(
        string providerPath, string providerName, string apiKey, int countryId, CancellationToken ct)
    {
        var resp = await _http.PostAsJsonAsync(
            $"/{providerPath}/operators",
            new HeroSmsOperatorsRequest { ApiKey = apiKey, CountryId = countryId },
            ct);
        if (!resp.IsSuccessStatusCode)
        {
            var detail = await resp.Content.ReadAsStringAsync(ct);
            throw new InvalidOperationException(
                $"Unable to load {providerName} operators ({(int)resp.StatusCode}): {detail}");
        }

        return await resp.Content.ReadFromJsonAsync<HeroSmsOperatorsDto>(ct)
            ?? throw new InvalidOperationException($"{providerName} returned an empty operators response");
    }

    public async Task<HeroSmsPriceDto> GetHeroSmsTelegramPriceAsync(
        string apiKey, int countryId, CancellationToken ct = default) =>
        await GetSmsProviderTelegramPriceAsync("hero_sms", "Hero SMS", apiKey, countryId, ct);

    public async Task<HeroSmsPriceDto> GetSmsPoolTelegramPriceAsync(
        string apiKey, int countryId, CancellationToken ct = default) =>
        await GetSmsProviderTelegramPriceAsync("sms_pool", "SMSpool", apiKey, countryId, ct);

    public async Task<HeroSmsPriceDto> GetGrizzlySmsTelegramPriceAsync(
        string apiKey, int countryId, CancellationToken ct = default) =>
        await GetSmsProviderTelegramPriceAsync("grizzly_sms", "GrizzlySMS", apiKey, countryId, ct);

    private async Task<HeroSmsPriceDto> GetSmsProviderTelegramPriceAsync(
        string providerPath, string providerName, string apiKey, int countryId, CancellationToken ct)
    {
        var resp = await _http.PostAsJsonAsync(
            $"/{providerPath}/telegram-price",
            new HeroSmsPriceRequest
            {
                ApiKey = apiKey,
                CountryId = countryId,
            },
            ct);
        if (!resp.IsSuccessStatusCode)
        {
            var detail = await resp.Content.ReadAsStringAsync(ct);
            throw new InvalidOperationException(
                $"Unable to load the {providerName} Telegram price ({(int)resp.StatusCode}): {detail}");
        }

        return await resp.Content.ReadFromJsonAsync<HeroSmsPriceDto>(ct)
            ?? throw new InvalidOperationException($"{providerName} returned an empty Telegram price response");
    }

    public async Task<HeroSmsActivationStartResponse> StartHeroSmsActivationsAsync(
        HeroSmsActivationStartRequest request, CancellationToken ct = default) =>
        await StartSmsProviderActivationsAsync("hero_sms", "Hero SMS", request, ct);

    public async Task<HeroSmsActivationStartResponse> StartSmsPoolActivationsAsync(
        HeroSmsActivationStartRequest request, CancellationToken ct = default) =>
        await StartSmsProviderActivationsAsync("sms_pool", "SMSpool", request, ct);

    public async Task<HeroSmsActivationStartResponse> StartGrizzlySmsActivationsAsync(
        HeroSmsActivationStartRequest request, CancellationToken ct = default) =>
        await StartSmsProviderActivationsAsync("grizzly_sms", "GrizzlySMS", request, ct);

    private async Task<HeroSmsActivationStartResponse> StartSmsProviderActivationsAsync(
        string providerPath, string providerName, HeroSmsActivationStartRequest request, CancellationToken ct)
    {
        var resp = await _http.PostAsJsonAsync($"/{providerPath}/activations/start", request, ct);
        if (!resp.IsSuccessStatusCode)
        {
            var detail = await resp.Content.ReadAsStringAsync(ct);
            throw new InvalidOperationException(
                $"Unable to start {providerName} activations ({(int)resp.StatusCode}): {detail}");
        }
        return await resp.Content.ReadFromJsonAsync<HeroSmsActivationStartResponse>(ct)
            ?? throw new InvalidOperationException("Backend returned an empty activation response");
    }

    public async Task<HeroSmsActivationStatusDto> GetHeroSmsActivationStatusAsync(
        CancellationToken ct = default) =>
        await GetSmsProviderActivationStatusAsync("hero_sms", ct);

    public async Task<HeroSmsActivationStatusDto> GetSmsPoolActivationStatusAsync(
        CancellationToken ct = default) =>
        await GetSmsProviderActivationStatusAsync("sms_pool", ct);

    public async Task<HeroSmsActivationStatusDto> GetGrizzlySmsActivationStatusAsync(
        CancellationToken ct = default) =>
        await GetSmsProviderActivationStatusAsync("grizzly_sms", ct);

    private async Task<HeroSmsActivationStatusDto> GetSmsProviderActivationStatusAsync(
        string providerPath, CancellationToken ct) =>
        await _http.GetFromJsonAsync<HeroSmsActivationStatusDto>(
            $"/{providerPath}/activations/status", ct) ?? new HeroSmsActivationStatusDto();

    public async Task StopHeroSmsActivationsAsync(CancellationToken ct = default)
    {
        await StopSmsProviderActivationsAsync("hero_sms", ct);
    }

    public async Task StopSmsPoolActivationsAsync(CancellationToken ct = default) =>
        await StopSmsProviderActivationsAsync("sms_pool", ct);

    public async Task StopGrizzlySmsActivationsAsync(CancellationToken ct = default) =>
        await StopSmsProviderActivationsAsync("grizzly_sms", ct);

    private async Task StopSmsProviderActivationsAsync(string providerPath, CancellationToken ct)
    {
        var resp = await _http.PostAsync($"/{providerPath}/activations/stop", null, ct);
        resp.EnsureSuccessStatusCode();
    }

    public async Task ClearHeroSmsActivationsAsync(CancellationToken ct = default)
    {
        await ClearSmsProviderActivationsAsync("hero_sms", ct);
    }

    public async Task ClearSmsPoolActivationsAsync(CancellationToken ct = default) =>
        await ClearSmsProviderActivationsAsync("sms_pool", ct);

    public async Task ClearGrizzlySmsActivationsAsync(CancellationToken ct = default) =>
        await ClearSmsProviderActivationsAsync("grizzly_sms", ct);

    private async Task ClearSmsProviderActivationsAsync(string providerPath, CancellationToken ct)
    {
        var resp = await _http.PostAsync($"/{providerPath}/activations/clear", null, ct);
        resp.EnsureSuccessStatusCode();
    }

    public async Task SubmitHeroSmsTwoFactorAsync(
        string rowId, string password, CancellationToken ct = default) =>
        await SubmitSmsProviderTwoFactorAsync("hero_sms", rowId, password, ct);

    public async Task SubmitSmsPoolTwoFactorAsync(
        string rowId, string password, CancellationToken ct = default) =>
        await SubmitSmsProviderTwoFactorAsync("sms_pool", rowId, password, ct);

    public async Task SubmitGrizzlySmsTwoFactorAsync(
        string rowId, string password, CancellationToken ct = default) =>
        await SubmitSmsProviderTwoFactorAsync("grizzly_sms", rowId, password, ct);

    private async Task SubmitSmsProviderTwoFactorAsync(
        string providerPath, string rowId, string password, CancellationToken ct)
    {
        var resp = await _http.PostAsJsonAsync(
            $"/{providerPath}/activations/{Uri.EscapeDataString(rowId)}/two-factor",
            new HeroSmsTwoFactorRequest { Password = password },
            ct);
        if (!resp.IsSuccessStatusCode)
        {
            var detail = await resp.Content.ReadAsStringAsync(ct);
            throw new InvalidOperationException(
                $"Unable to submit Telegram 2-step verification ({(int)resp.StatusCode}): {detail}");
        }
    }

    public Task AssignRoleAsync(string phone, string role, CancellationToken ct = default) =>
        PostVoidAsync($"/accounts/{Uri.EscapeDataString(phone)}/role", new AssignValueRequest { Value = role }, ct);

    public Task AssignFolderAsync(string phone, string folder, CancellationToken ct = default) =>
        PostVoidAsync($"/accounts/{Uri.EscapeDataString(phone)}/folder", new AssignValueRequest { Value = folder }, ct);

    public async Task<RecheckResponse> RecheckAsync(
        List<string>? phones = null, bool deep = false, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync(
            "/accounts/recheck", new RecheckRequest { Phones = phones, Deep = deep }, ct);
        resp.EnsureSuccessStatusCode();
        return (await resp.Content.ReadFromJsonAsync<RecheckResponse>(ct))!;
    }

    /// <summary>Re-scans ACCOUNTS_DIR/SPARE_ACCOUNTS_DIR for .session+.json pairs dropped in since startup.</summary>
    public async Task<RescanResponse> RescanAccountsAsync(CancellationToken ct = default)
    {
        var resp = await _http.PostAsync("/accounts/rescan", content: null, ct);
        resp.EnsureSuccessStatusCode();
        return (await resp.Content.ReadFromJsonAsync<RescanResponse>(ct))!;
    }

    private async Task PostVoidAsync<T>(string path, T body, CancellationToken ct)
    {
        var resp = await _http.PostAsJsonAsync(path, body, ct);
        resp.EnsureSuccessStatusCode();
    }

    public async Task<ProxyCheckStartResponse> StartProxyCheckAsync(
        ProxyCheckStartRequest request, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/proxy_check/start", request, ct);
        if (!resp.IsSuccessStatusCode)
        {
            var detail = await resp.Content.ReadAsStringAsync(ct);
            throw new InvalidOperationException(string.Format(
                LocalizationService.Instance["BackendClient.StartProxyCheckErrorFormat"], (int)resp.StatusCode, detail));
        }
        return (await resp.Content.ReadFromJsonAsync<ProxyCheckStartResponse>(ct))!;
    }

    public async Task<ProxyCheckStatusDto> GetProxyCheckStatusAsync(CancellationToken ct = default)
    {
        var result = await _http.GetFromJsonAsync<ProxyCheckStatusDto>("/proxy_check/status", ct);
        return result ?? new ProxyCheckStatusDto();
    }

    public async Task<List<StoredProxyDto>> GetStoredProxiesAsync(CancellationToken ct = default)
    {
        return await _http.GetFromJsonAsync<List<StoredProxyDto>>("/proxies", ct) ?? new();
    }

    public async Task<List<StoredProxyDto>> AddStoredProxiesAsync(
        ProxyBulkCreateRequest request, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/proxies", request, ct);
        await EnsureProxySuccessAsync(resp, ct);
        return await resp.Content.ReadFromJsonAsync<List<StoredProxyDto>>(ct) ?? new();
    }

    public async Task<ProxyCheckStartResponse> StartStoredProxyCheckAsync(
        StoredProxyCheckRequest request, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/proxies/check", request, ct);
        await EnsureProxySuccessAsync(resp, ct);
        return (await resp.Content.ReadFromJsonAsync<ProxyCheckStartResponse>(ct))!;
    }

    public async Task<StoredProxyCheckStatusDto> GetStoredProxyCheckStatusAsync(
        CancellationToken ct = default)
    {
        return await _http.GetFromJsonAsync<StoredProxyCheckStatusDto>(
            "/proxies/check/status", ct) ?? new();
    }

    public async Task<ProxyDeleteResponse> DeleteStoredProxyAsync(
        int proxyId, CancellationToken ct = default)
    {
        var resp = await _http.DeleteAsync($"/proxies/{proxyId}", ct);
        await EnsureProxySuccessAsync(resp, ct);
        return (await resp.Content.ReadFromJsonAsync<ProxyDeleteResponse>(ct))!;
    }

    public async Task<ProxyDeleteResponse> DeleteAllStoredProxiesAsync(CancellationToken ct = default)
    {
        var resp = await _http.DeleteAsync("/proxies", ct);
        await EnsureProxySuccessAsync(resp, ct);
        return (await resp.Content.ReadFromJsonAsync<ProxyDeleteResponse>(ct))!;
    }

    public async Task<ProxyDeleteResponse> DeleteBadStoredProxiesAsync(CancellationToken ct = default)
    {
        var resp = await _http.DeleteAsync("/proxies/bad", ct);
        await EnsureProxySuccessAsync(resp, ct);
        return (await resp.Content.ReadFromJsonAsync<ProxyDeleteResponse>(ct))!;
    }

    private static async Task EnsureProxySuccessAsync(
        HttpResponseMessage response, CancellationToken ct)
    {
        if (response.IsSuccessStatusCode)
            return;
        var detail = await response.Content.ReadAsStringAsync(ct);
        throw new InvalidOperationException(string.Format(
            LocalizationService.Instance["BackendClient.StartProxyCheckErrorFormat"],
            (int)response.StatusCode,
            detail));
    }

    public async Task<ProxyPoolCheckStartResponse> StartProxyPoolCheckAsync(
        ProxyPoolCheckStartRequest request, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/proxy_pool_check/start", request, ct);
        if (!resp.IsSuccessStatusCode)
        {
            var detail = await resp.Content.ReadAsStringAsync(ct);
            throw new InvalidOperationException(string.Format(
                LocalizationService.Instance["BackendClient.StartProxyCheckErrorFormat"], (int)resp.StatusCode, detail));
        }
        return (await resp.Content.ReadFromJsonAsync<ProxyPoolCheckStartResponse>(ct))!;
    }

    public async Task<ProxyPoolCheckStatusDto> GetProxyPoolCheckStatusAsync(CancellationToken ct = default)
    {
        var result = await _http.GetFromJsonAsync<ProxyPoolCheckStatusDto>("/proxy_pool_check/status", ct);
        return result ?? new ProxyPoolCheckStatusDto();
    }

    public async Task<TdataConvertStartResponse> StartTdataConvertAsync(
        TdataConvertStartRequest request, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/tdata_convert/start", request, ct);
        if (!resp.IsSuccessStatusCode)
        {
            var detail = await resp.Content.ReadAsStringAsync(ct);
            throw new InvalidOperationException(string.Format(
                LocalizationService.Instance["BackendClient.StartConversionErrorFormat"], (int)resp.StatusCode, detail));
        }
        return (await resp.Content.ReadFromJsonAsync<TdataConvertStartResponse>(ct))!;
    }

    public async Task<TdataConvertStatusDto> GetTdataConvertStatusAsync(CancellationToken ct = default)
    {
        var result = await _http.GetFromJsonAsync<TdataConvertStatusDto>("/tdata_convert/status", ct);
        return result ?? new TdataConvertStatusDto();
    }

    public async Task<SessionConvertStartResponse> StartSessionConvertAsync(
        SessionConvertStartRequest request, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/session_convert/start", request, ct);
        if (!resp.IsSuccessStatusCode)
        {
            var detail = await resp.Content.ReadAsStringAsync(ct);
            throw new InvalidOperationException(string.Format(
                LocalizationService.Instance["BackendClient.StartConversionErrorFormat"], (int)resp.StatusCode, detail));
        }
        return (await resp.Content.ReadFromJsonAsync<SessionConvertStartResponse>(ct))!;
    }

    public async Task<SessionConvertStatusDto> GetSessionConvertStatusAsync(CancellationToken ct = default)
    {
        var result = await _http.GetFromJsonAsync<SessionConvertStatusDto>("/session_convert/status", ct);
        return result ?? new SessionConvertStatusDto();
    }

    public async Task<JsonGeneratorStartResponse> StartJsonGeneratorAsync(
        JsonGeneratorStartRequest request, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/json_generator/start", request, ct);
        if (!resp.IsSuccessStatusCode)
        {
            var detail = await resp.Content.ReadAsStringAsync(ct);
            throw new InvalidOperationException($"Unable to start JSON generation ({(int)resp.StatusCode}): {detail}");
        }
        return (await resp.Content.ReadFromJsonAsync<JsonGeneratorStartResponse>(ct))!;
    }

    public async Task<JsonGeneratorStatusDto> GetJsonGeneratorStatusAsync(CancellationToken ct = default) =>
        await _http.GetFromJsonAsync<JsonGeneratorStatusDto>("/json_generator/status", ct)
        ?? new JsonGeneratorStatusDto();

    public async Task StopJsonGeneratorAsync(CancellationToken ct = default)
    {
        var resp = await _http.PostAsync("/json_generator/stop", null, ct);
        resp.EnsureSuccessStatusCode();
    }

    public async Task ClearJsonGeneratorAsync(CancellationToken ct = default)
    {
        var resp = await _http.PostAsync("/json_generator/clear", null, ct);
        resp.EnsureSuccessStatusCode();
    }

    public async Task<ParseStartResponse> StartParsingAsync(ParseStartRequest request, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/parsing/start", request, ct);
        if (!resp.IsSuccessStatusCode)
        {
            var detail = await resp.Content.ReadAsStringAsync(ct);
            throw new InvalidOperationException(string.Format(
                LocalizationService.Instance["BackendClient.StartParsingErrorFormat"], (int)resp.StatusCode, detail));
        }
        return (await resp.Content.ReadFromJsonAsync<ParseStartResponse>(ct))!;
    }

    public async Task StopParsingAsync(CancellationToken ct = default)
    {
        var resp = await _http.PostAsync("/parsing/stop", content: null, ct);
        resp.EnsureSuccessStatusCode();
    }

    public async Task<ParseStatusDto> GetParsingStatusAsync(CancellationToken ct = default)
    {
        var result = await _http.GetFromJsonAsync<ParseStatusDto>("/parsing/status", ct);
        return result ?? new ParseStatusDto();
    }

    public async Task<List<ParseSourceOut>> GetParsingSourcesAsync(int limit = 200, CancellationToken ct = default)
    {
        var resp = await _http.GetAsync($"/parsing/sources?limit={limit}", ct);
        if (!resp.IsSuccessStatusCode)
        {
            var detail = await resp.Content.ReadAsStringAsync(ct);
            throw new InvalidOperationException(
                $"Unable to load parsing sources ({(int)resp.StatusCode}): {detail}");
        }
        var result = await resp.Content.ReadFromJsonAsync<ParseSourcesResponse>(ct);
        return result?.Sources ?? new List<ParseSourceOut>();
    }

    public async Task<InviteByNumberStartResponse> StartInviteByNumberAsync(
        InviteByNumberStartRequest request, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/invite_by_number/start", request, ct);
        if (!resp.IsSuccessStatusCode)
        {
            var detail = await resp.Content.ReadAsStringAsync(ct);
            throw new InvalidOperationException(
                $"Invite by number start failed ({(int)resp.StatusCode}): {detail}");
        }
        return (await resp.Content.ReadFromJsonAsync<InviteByNumberStartResponse>(ct))!;
    }

    public async Task StopInviteByNumberAsync(CancellationToken ct = default)
    {
        var resp = await _http.PostAsync("/invite_by_number/stop", content: null, ct);
        resp.EnsureSuccessStatusCode();
    }

    public async Task<InviteByNumberStatusDto> GetInviteByNumberStatusAsync(CancellationToken ct = default)
    {
        var result = await _http.GetFromJsonAsync<InviteByNumberStatusDto>("/invite_by_number/status", ct);
        return result ?? new InviteByNumberStatusDto();
    }

    public async Task<SendByNumbersStartResponse> StartSendByNumbersAsync(
        SendByNumbersStartRequest request, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/send_by_numbers/start", request, ct);
        if (!resp.IsSuccessStatusCode)
        {
            var detail = await resp.Content.ReadAsStringAsync(ct);
            throw new InvalidOperationException(
                $"Send by numbers start failed ({(int)resp.StatusCode}): {detail}");
        }
        return (await resp.Content.ReadFromJsonAsync<SendByNumbersStartResponse>(ct))!;
    }

    public async Task StopSendByNumbersAsync(CancellationToken ct = default)
    {
        var resp = await _http.PostAsync("/send_by_numbers/stop", content: null, ct);
        resp.EnsureSuccessStatusCode();
    }

    public async Task<SendByNumbersStatusDto> GetSendByNumbersStatusAsync(CancellationToken ct = default)
    {
        var result = await _http.GetFromJsonAsync<SendByNumbersStatusDto>("/send_by_numbers/status", ct);
        return result ?? new SendByNumbersStatusDto();
    }

    public async Task<NumberCheckerStartResponse> StartNumberCheckerAsync(
        NumberCheckerStartRequest request, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/number_checker/start", request, ct);
        if (!resp.IsSuccessStatusCode)
        {
            var detail = await resp.Content.ReadAsStringAsync(ct);
            throw new InvalidOperationException(
                $"Number checker start failed ({(int)resp.StatusCode}): {detail}");
        }
        return (await resp.Content.ReadFromJsonAsync<NumberCheckerStartResponse>(ct))!;
    }

    public async Task StopNumberCheckerAsync(CancellationToken ct = default)
    {
        var resp = await _http.PostAsync("/number_checker/stop", content: null, ct);
        resp.EnsureSuccessStatusCode();
    }

    public async Task<NumberCheckerStatusDto> GetNumberCheckerStatusAsync(
        CancellationToken ct = default)
    {
        var result = await _http.GetFromJsonAsync<NumberCheckerStatusDto>(
            "/number_checker/status", ct);
        return result ?? new NumberCheckerStatusDto();
    }

    public async Task<SendByIdStartResponse> StartSendByIdAsync(
        SendByIdStartRequest request, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/send_by_id/start", request, ct);
        if (!resp.IsSuccessStatusCode)
        {
            var detail = await resp.Content.ReadAsStringAsync(ct);
            throw new InvalidOperationException(
                $"Sending SMS by ID start failed ({(int)resp.StatusCode}): {detail}");
        }
        return (await resp.Content.ReadFromJsonAsync<SendByIdStartResponse>(ct))!;
    }

    public async Task StopSendByIdAsync(CancellationToken ct = default)
    {
        var resp = await _http.PostAsync("/send_by_id/stop", content: null, ct);
        resp.EnsureSuccessStatusCode();
    }

    public async Task<SendByIdStatusDto> GetSendByIdStatusAsync(CancellationToken ct = default)
    {
        var result = await _http.GetFromJsonAsync<SendByIdStatusDto>("/send_by_id/status", ct);
        return result ?? new SendByIdStatusDto();
    }
}
