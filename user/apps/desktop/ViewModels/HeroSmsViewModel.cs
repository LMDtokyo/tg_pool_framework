using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Globalization;
using System.Net.Http;
using System.Windows.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using TgPoolLauncher.Localization;
using TgPoolLauncher.Models;
using TgPoolLauncher.Services;

namespace TgPoolLauncher.ViewModels;

public sealed record SmsActivationProviderConfig(
    string Name,
    string Host,
    string AccountHeaderKey,
    string ApiKeyToolTipKey,
    string KeyPrivacyMessageKey,
    string IntegrationBehaviorTitleKey,
    string PurchaseWarningKey,
    string PriceAvailabilityNoteKey,
    string AvailabilityLabelKey,
    bool AvailabilityIsPercent,
    bool RequiresAvailabilityCount,
    Func<BackendClient, string, CancellationToken, Task<HeroSmsBalanceDto>> LoadBalance,
    Func<BackendClient, string, CancellationToken, Task<List<HeroSmsCountryDto>>> LoadCountries,
    Func<BackendClient, string, int, CancellationToken, Task<HeroSmsOperatorsDto>> LoadOperators,
    Func<BackendClient, string, int, CancellationToken, Task<HeroSmsPriceDto>> LoadTelegramPrice,
    Func<BackendClient, HeroSmsActivationStartRequest, CancellationToken, Task<HeroSmsActivationStartResponse>> StartActivations,
    Func<BackendClient, CancellationToken, Task<HeroSmsActivationStatusDto>> GetActivationStatus,
    Func<BackendClient, CancellationToken, Task> StopActivations,
    Func<BackendClient, CancellationToken, Task> ClearActivations,
    Func<BackendClient, string, string, CancellationToken, Task> SubmitTwoFactor)
{
    public static SmsActivationProviderConfig HeroSms { get; } = new(
        "Hero SMS",
        "hero-sms.com",
        "HeroSms.AccountHeader",
        "HeroSms.ApiKeyTooltip",
        "HeroSms.ApiKeyNote",
        "HeroSms.ImportantInfoSubheader",
        "HeroSms.RealPurchasesText",
        "HeroSms.PriceAvailabilityText",
        "HeroSms.AvailabilityLabel",
        false,
        true,
        (backend, apiKey, ct) => backend.GetHeroSmsBalanceAsync(apiKey, ct),
        (backend, apiKey, ct) => backend.GetHeroSmsCountriesAsync(apiKey, ct),
        (backend, apiKey, countryId, ct) => backend.GetHeroSmsOperatorsAsync(apiKey, countryId, ct),
        (backend, apiKey, countryId, ct) => backend.GetHeroSmsTelegramPriceAsync(apiKey, countryId, ct),
        (backend, request, ct) => backend.StartHeroSmsActivationsAsync(request, ct),
        (backend, ct) => backend.GetHeroSmsActivationStatusAsync(ct),
        (backend, ct) => backend.StopHeroSmsActivationsAsync(ct),
        (backend, ct) => backend.ClearHeroSmsActivationsAsync(ct),
        (backend, rowId, password, ct) => backend.SubmitHeroSmsTwoFactorAsync(rowId, password, ct));

    public static SmsActivationProviderConfig SmsPool { get; } = new(
        "SMSpool",
        "smspool.net",
        "HeroSms.SmsPool.AccountHeader",
        "HeroSms.SmsPool.ApiKeyToolTip",
        "HeroSms.SmsPool.KeyPrivacyMessage",
        "HeroSms.SmsPool.IntegrationBehaviorTitle",
        "HeroSms.SmsPool.PurchaseWarning",
        "HeroSms.SmsPool.PriceAvailabilityNote",
        "HeroSms.SmsPool.AvailabilityLabel",
        true,
        false,
        (backend, apiKey, ct) => backend.GetSmsPoolBalanceAsync(apiKey, ct),
        (backend, apiKey, ct) => backend.GetSmsPoolCountriesAsync(apiKey, ct),
        (backend, apiKey, countryId, ct) => backend.GetSmsPoolOperatorsAsync(apiKey, countryId, ct),
        (backend, apiKey, countryId, ct) => backend.GetSmsPoolTelegramPriceAsync(apiKey, countryId, ct),
        (backend, request, ct) => backend.StartSmsPoolActivationsAsync(request, ct),
        (backend, ct) => backend.GetSmsPoolActivationStatusAsync(ct),
        (backend, ct) => backend.StopSmsPoolActivationsAsync(ct),
        (backend, ct) => backend.ClearSmsPoolActivationsAsync(ct),
        (backend, rowId, password, ct) => backend.SubmitSmsPoolTwoFactorAsync(rowId, password, ct));

    public static SmsActivationProviderConfig GrizzlySms { get; } = new(
        "GrizzlySMS",
        "grizzlysms.com",
        "HeroSms.GrizzlySms.AccountHeader",
        "HeroSms.GrizzlySms.ApiKeyToolTip",
        "HeroSms.GrizzlySms.KeyPrivacyMessage",
        "HeroSms.GrizzlySms.IntegrationBehaviorTitle",
        "HeroSms.GrizzlySms.PurchaseWarning",
        "HeroSms.GrizzlySms.PriceAvailabilityNote",
        "HeroSms.AvailabilityLabel",
        false,
        true,
        (backend, apiKey, ct) => backend.GetGrizzlySmsBalanceAsync(apiKey, ct),
        (backend, apiKey, ct) => backend.GetGrizzlySmsCountriesAsync(apiKey, ct),
        (backend, apiKey, countryId, ct) => backend.GetGrizzlySmsOperatorsAsync(apiKey, countryId, ct),
        (backend, apiKey, countryId, ct) => backend.GetGrizzlySmsTelegramPriceAsync(apiKey, countryId, ct),
        (backend, request, ct) => backend.StartGrizzlySmsActivationsAsync(request, ct),
        (backend, ct) => backend.GetGrizzlySmsActivationStatusAsync(ct),
        (backend, ct) => backend.StopGrizzlySmsActivationsAsync(ct),
        (backend, ct) => backend.ClearGrizzlySmsActivationsAsync(ct),
        (backend, rowId, password, ct) => backend.SubmitGrizzlySmsTwoFactorAsync(rowId, password, ct));
}

public partial class HeroSmsViewModel : ObservableObject
{
    private readonly BackendClient _backend;
    private readonly SmsActivationProviderConfig _provider;
    private readonly DispatcherTimer _statusTimer;
    private List<HeroSmsCountryDto> _countryDtos = [];
    private CancellationTokenSource? _catalogLoadCts;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(LoadCountriesCommand))]
    [NotifyCanExecuteChangedFor(nameof(LoadBalanceCommand))]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string apiKey = "";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(LoadCountriesCommand))]
    private bool isLoadingCountries;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(LoadBalanceCommand))]
    private bool isLoadingBalance;

    [ObservableProperty]
    private string balanceDisplay = LocalizationService.Instance["HeroSms.BalancePlaceholder"];

    [ObservableProperty]
    private string balanceErrorMessage = "";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private HeroSmsCountryOption? selectedCountry;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private HeroSmsOperatorOption? selectedOperator;

    [ObservableProperty]
    private bool isLoadingCatalog;

    [ObservableProperty]
    private string catalogStatusMessage = "";

    [ObservableProperty]
    private string catalogErrorMessage = "";

    [ObservableProperty]
    private string countriesStatusMessage = "";

    [ObservableProperty]
    private string countriesErrorMessage = "";

    [ObservableProperty]
    private string countrySearchText = "";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private HeroSmsPriceOption? selectedPriceOption;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private HeroSmsPriceOption? selectedCeilingOption;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private int numbersAvailable;

    [ObservableProperty]
    private string availabilityDisplay = "0";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private int targetAccountCount = 1;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private int concurrentPhoneCount = 5;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private int smsTimeout = 300;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    [NotifyCanExecuteChangedFor(nameof(StopCommand))]
    [NotifyCanExecuteChangedFor(nameof(ClearCommand))]
    private bool isRunning;

    [ObservableProperty]
    private string operationStatusMessage = "";

    [ObservableProperty]
    private string operationErrorMessage = "";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(SubmitTwoFactorCommand))]
    private HeroSmsActivationRowDto? selectedActivityRow;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(SubmitTwoFactorCommand))]
    private string twoFactorPassword = "";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(SubmitTwoFactorCommand))]
    private bool isSubmittingTwoFactor;

    public ObservableCollection<HeroSmsCountryOption> Countries { get; } = new();
    public ObservableCollection<HeroSmsOperatorOption> Operators { get; } = new();
    public ObservableCollection<HeroSmsPriceOption> PriceOptions { get; } = new();
    public ObservableCollection<HeroSmsPriceOption> CeilingPriceOptions { get; } = new();
    public ObservableCollection<HeroSmsActivationRowDto> ActivityRows { get; } = new();

    public int EventCount => ActivityRows.Count;
    public string ProviderName => _provider.Name;
    public string ProviderHost => _provider.Host;
    public string AccountHeader => LocalizationService.Instance[_provider.AccountHeaderKey];
    public string ApiKeyToolTip => LocalizationService.Instance[_provider.ApiKeyToolTipKey];
    public string KeyPrivacyMessage => LocalizationService.Instance[_provider.KeyPrivacyMessageKey];
    public string IntegrationBehaviorTitle => LocalizationService.Instance[_provider.IntegrationBehaviorTitleKey];
    public string PurchaseWarning => LocalizationService.Instance[_provider.PurchaseWarningKey];
    public string PriceAvailabilityNote => LocalizationService.Instance[_provider.PriceAvailabilityNoteKey];
    public string AvailabilityLabel => LocalizationService.Instance[_provider.AvailabilityLabelKey];

    public HeroSmsViewModel(BackendClient backend)
        : this(backend, SmsActivationProviderConfig.HeroSms)
    {
    }

    protected HeroSmsViewModel(
        BackendClient backend,
        SmsActivationProviderConfig provider)
    {
        _backend = backend;
        _provider = provider;
        ResetCountries();
        ResetOperators();
        LocalizationService.Instance.PropertyChanged += OnLanguageChanged;

        _statusTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        _statusTimer.Tick += async (_, _) => await RefreshActivationStatusAsync();
        _statusTimer.Start();
    }

    private void OnLanguageChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName != nameof(LocalizationService.CurrentLanguage))
            return;

        RebuildCountryOptions();
        OnPropertyChanged(nameof(AccountHeader));
        OnPropertyChanged(nameof(ApiKeyToolTip));
        OnPropertyChanged(nameof(KeyPrivacyMessage));
        OnPropertyChanged(nameof(IntegrationBehaviorTitle));
        OnPropertyChanged(nameof(PurchaseWarning));
        OnPropertyChanged(nameof(PriceAvailabilityNote));
        OnPropertyChanged(nameof(AvailabilityLabel));
    }

    partial void OnApiKeyChanged(string? oldValue, string newValue)
    {
        if (string.Equals(oldValue, newValue, StringComparison.Ordinal))
            return;

        _catalogLoadCts?.Cancel();
        BalanceDisplay = LocalizationService.Instance["HeroSms.BalancePlaceholder"];
        BalanceErrorMessage = "";
        CountriesStatusMessage = "";
        CountriesErrorMessage = "";
        CountrySearchText = "";
        _countryDtos = [];
        ResetCountries();
        ResetOperators();
        ResetCatalog();
    }

    partial void OnCountrySearchTextChanged(string value)
    {
        RebuildCountryOptions();
        UpdateCountriesStatusMessage();
    }

    partial void OnSelectedCountryChanged(
        HeroSmsCountryOption? oldValue,
        HeroSmsCountryOption? newValue)
    {
        if (oldValue?.Id == newValue?.Id)
            return;

        _catalogLoadCts?.Cancel();
        ResetOperators();
        ResetCatalog();
        if (newValue is { IsPlaceholder: false, Id: >= 0 }
            && !string.IsNullOrWhiteSpace(ApiKey))
        {
            _ = LoadCountryCatalogAsync(newValue.Id);
        }
    }

    private bool CanLoadCountries() =>
        !IsLoadingCountries && !string.IsNullOrWhiteSpace(ApiKey);

    private bool CanLoadBalance() =>
        !IsLoadingBalance && !string.IsNullOrWhiteSpace(ApiKey);

    private bool CanStart() =>
        !IsRunning
        && !string.IsNullOrWhiteSpace(ApiKey)
        && SelectedCountry is { IsPlaceholder: false, Id: >= 0 }
        && SelectedOperator is { IsPlaceholder: false }
        && SelectedPriceOption is { Price: > 0 }
        && SelectedCeilingOption is { Price: > 0 }
        && SelectedCeilingOption.Price >= SelectedPriceOption.Price
        && (!_provider.RequiresAvailabilityCount || NumbersAvailable > 0)
        && TargetAccountCount >= 1
        && ConcurrentPhoneCount is >= 1 and <= 10
        && SmsTimeout is >= 30 and <= 1200;

    private bool CanStop() => IsRunning;
    private bool CanClear() => !IsRunning && ActivityRows.Count > 0;
    private bool CanSubmitTwoFactor() =>
        !IsSubmittingTwoFactor
        && SelectedActivityRow is { NeedsTwoFactor: true }
        && !string.IsNullOrWhiteSpace(TwoFactorPassword);

    [RelayCommand(CanExecute = nameof(CanLoadBalance))]
    private async Task LoadBalanceAsync()
    {
        BalanceErrorMessage = "";
        IsLoadingBalance = true;
        try
        {
            var result = await _provider.LoadBalance(_backend, ApiKey.Trim(), CancellationToken.None);
            BalanceDisplay = string.Format(
                LocalizationService.Instance["HeroSms.BalanceFormat"],
                result.Balance.ToString("0.00", CultureInfo.InvariantCulture));
        }
        catch (Exception ex)
        {
            BalanceDisplay = LocalizationService.Instance["HeroSms.BalancePlaceholder"];
            BalanceErrorMessage = ex.Message;
        }
        finally
        {
            IsLoadingBalance = false;
        }
    }

    [RelayCommand(CanExecute = nameof(CanLoadCountries))]
    private async Task LoadCountriesAsync()
    {
        CountriesStatusMessage = "";
        CountriesErrorMessage = "";
        IsLoadingCountries = true;
        try
        {
            _countryDtos = await _provider.LoadCountries(_backend, ApiKey.Trim(), CancellationToken.None);
            RebuildCountryOptions();
            UpdateCountriesStatusMessage();
        }
        catch (Exception ex)
        {
            _countryDtos = [];
            ResetCountries();
            CountriesErrorMessage = ex.Message;
        }
        finally
        {
            IsLoadingCountries = false;
        }
    }

    [RelayCommand]
    private async Task RefreshCatalogAsync()
    {
        if (SelectedCountry is { IsPlaceholder: false } country)
            await LoadCountryCatalogAsync(country.Id);
    }

    private async Task LoadCountryCatalogAsync(int countryId)
    {
        _catalogLoadCts?.Cancel();
        var loadCts = new CancellationTokenSource();
        _catalogLoadCts = loadCts;
        CatalogStatusMessage = "";
        CatalogErrorMessage = "";
        IsLoadingCatalog = true;
        try
        {
            var operatorsTask = _provider.LoadOperators(
                _backend, ApiKey.Trim(), countryId, loadCts.Token);
            var priceTask = _provider.LoadTelegramPrice(
                _backend, ApiKey.Trim(), countryId, loadCts.Token);
            await Task.WhenAll(operatorsTask, priceTask);

            if (SelectedCountry?.Id != countryId)
                return;

            Operators.Clear();
            Operators.Add(new HeroSmsOperatorOption("any", LocalizationService.Instance["HeroSms.AnyOperatorOption"]));
            foreach (var value in operatorsTask.Result.Operators)
            {
                if (!value.Equals("any", StringComparison.OrdinalIgnoreCase))
                    Operators.Add(new HeroSmsOperatorOption(value, value));
            }
            SelectedOperator = Operators[0];

            ApplyPriceCatalog(priceTask.Result);
            CatalogStatusMessage = SelectedPriceOption is null
                ? LocalizationService.Instance["HeroSms.TelegramUnavailableInCountry"]
                : string.Format(
                    LocalizationService.Instance["HeroSms.CatalogSummaryFormat"],
                    Operators.Count,
                    PriceOptions.Count,
                    AvailabilityLabel,
                    AvailabilityDisplay);
            StartCommand.NotifyCanExecuteChanged();
        }
        catch (OperationCanceledException) when (loadCts.IsCancellationRequested)
        {
        }
        catch (Exception ex)
        {
            if (SelectedCountry?.Id == countryId)
            {
                ResetOperators();
                ResetCatalog();
                CatalogErrorMessage = ex.Message;
            }
        }
        finally
        {
            if (ReferenceEquals(_catalogLoadCts, loadCts))
            {
                _catalogLoadCts = null;
                IsLoadingCatalog = false;
            }
            loadCts.Dispose();
        }
    }

    partial void OnSelectedPriceOptionChanged(
        HeroSmsPriceOption? oldValue,
        HeroSmsPriceOption? newValue)
    {
        if (ReferenceEquals(oldValue, newValue))
            return;

        NumbersAvailable = newValue?.Available ?? 0;
        AvailabilityDisplay = FormatAvailability(NumbersAvailable);
        RebuildCeilingPriceOptions(preserveSelection: true);
        StartCommand.NotifyCanExecuteChanged();
    }

    private void ApplyPriceCatalog(HeroSmsPriceDto offer)
    {
        PriceOptions.Clear();
        SelectedPriceOption = null;
        CeilingPriceOptions.Clear();
        SelectedCeilingOption = null;

        var tiers = offer.Offers
            .Where(item => item.Price > 0 && item.Available >= 0)
            .OrderBy(item => item.Price)
            .ToList();

        if (tiers.Count == 0 && offer.Price is decimal singlePrice and > 0)
        {
            tiers.Add(new HeroSmsPriceOfferDto
            {
                Price = singlePrice,
                Available = Math.Max(0, offer.Available),
            });
        }

        foreach (var tier in tiers)
        {
            PriceOptions.Add(new HeroSmsPriceOption(
                tier.Price,
                tier.Available,
                FormatPriceOption(tier.Price, tier.Available)));
        }

        if (PriceOptions.Count == 0)
        {
            NumbersAvailable = 0;
            AvailabilityDisplay = FormatAvailability(0);
            return;
        }

        HeroSmsPriceOption? preferred = null;
        if (offer.Price is decimal recommended and > 0)
        {
            preferred = PriceOptions.FirstOrDefault(option => option.Price == recommended)
                ?? PriceOptions.FirstOrDefault(option => option.Price >= recommended);
        }
        preferred ??= PriceOptions.FirstOrDefault(option => option.Available > 0)
            ?? PriceOptions[0];

        SelectedPriceOption = preferred;
        NumbersAvailable = preferred.Available;
        AvailabilityDisplay = FormatAvailability(preferred.Available);
        RebuildCeilingPriceOptions(preserveSelection: false);
    }

    private void RebuildCeilingPriceOptions(bool preserveSelection)
    {
        var previousCeiling = preserveSelection ? SelectedCeilingOption?.Price : null;
        CeilingPriceOptions.Clear();
        SelectedCeilingOption = null;

        if (SelectedPriceOption is not { Price: > 0 } start)
            return;

        foreach (var option in PriceOptions.Where(item => item.Price >= start.Price))
            CeilingPriceOptions.Add(option);

        if (CeilingPriceOptions.Count == 0)
        {
            CeilingPriceOptions.Add(start);
        }

        SelectedCeilingOption =
            CeilingPriceOptions.FirstOrDefault(option => option.Price == previousCeiling)
            ?? CeilingPriceOptions[^1];
    }

    private static string FormatPriceOption(decimal price, int available) =>
        string.Format(
            LocalizationService.Instance["HeroSms.PriceOptionFormat"],
            price.ToString("0.####", CultureInfo.InvariantCulture),
            available.ToString("N0", CultureInfo.InvariantCulture));

    [RelayCommand(CanExecute = nameof(CanStart))]
    private async Task StartAsync()
    {
        if (SelectedCountry is not { IsPlaceholder: false } country
            || SelectedOperator is not { IsPlaceholder: false } selectedOperator
            || SelectedPriceOption is not { Price: > 0 } selectedPrice
            || SelectedCeilingOption is not { Price: > 0 } selectedCeiling)
            return;

        OperationStatusMessage = "";
        OperationErrorMessage = "";
        try
        {
            await _provider.StartActivations(
                _backend,
                new HeroSmsActivationStartRequest
                {
                    ApiKey = ApiKey.Trim(),
                    CountryId = country.Id,
                    Operator = selectedOperator.Value,
                    TargetCount = TargetAccountCount,
                    Concurrency = ConcurrentPhoneCount,
                    TimeoutSec = SmsTimeout,
                    MaxPrice = selectedPrice.Price,
                    PriceCeiling = selectedCeiling.Price,
                    PriceOffers = PriceOptions
                        .Select(option => option.Price)
                        .Where(price => price > 0)
                        .Distinct()
                        .OrderBy(price => price)
                        .ToList(),
                },
                CancellationToken.None);
            IsRunning = true;
            OperationStatusMessage = string.Format(
                LocalizationService.Instance["HeroSms.RegistrationStartedFormat"],
                ProviderName);
            await RefreshActivationStatusAsync();
        }
        catch (Exception ex)
        {
            OperationErrorMessage = ex.Message;
        }
    }

    [RelayCommand(CanExecute = nameof(CanStop))]
    private async Task StopAsync()
    {
        try
        {
            OperationStatusMessage = LocalizationService.Instance["HeroSms.StoppingCanceling"];
            await _provider.StopActivations(_backend, CancellationToken.None);
            await RefreshActivationStatusAsync();
            OperationStatusMessage = string.Format(
                LocalizationService.Instance["HeroSms.ActivationBatchStoppedFormat"],
                ProviderName);
        }
        catch (Exception ex)
        {
            OperationErrorMessage = ex.Message;
        }
    }

    [RelayCommand(CanExecute = nameof(CanClear))]
    private async Task ClearAsync()
    {
        try
        {
            await _provider.ClearActivations(_backend, CancellationToken.None);
            ActivityRows.Clear();
            OnPropertyChanged(nameof(EventCount));
            ClearCommand.NotifyCanExecuteChanged();
            OperationStatusMessage = "";
            OperationErrorMessage = "";
        }
        catch (Exception ex)
        {
            OperationErrorMessage = ex.Message;
        }
    }

    [RelayCommand(CanExecute = nameof(CanSubmitTwoFactor))]
    private async Task SubmitTwoFactorAsync()
    {
        if (SelectedActivityRow is not { NeedsTwoFactor: true } row)
            return;

        IsSubmittingTwoFactor = true;
        OperationErrorMessage = "";
        try
        {
            await _provider.SubmitTwoFactor(
                _backend,
                row.RowId,
                TwoFactorPassword,
                CancellationToken.None);
            TwoFactorPassword = "";
            OperationStatusMessage = string.Format(
                LocalizationService.Instance["HeroSms.TwoFactorSubmittedFormat"],
                row.PhoneNumber);
            await RefreshActivationStatusAsync();
        }
        catch (Exception ex)
        {
            OperationErrorMessage = ex.Message;
        }
        finally
        {
            IsSubmittingTwoFactor = false;
        }
    }

    private async Task RefreshActivationStatusAsync()
    {
        try
        {
            var status = await _provider.GetActivationStatus(_backend, CancellationToken.None);
            IsRunning = status.Running;
            var selectedRowId = SelectedActivityRow?.RowId;
            ActivityRows.Clear();
            foreach (var row in status.Rows)
                ActivityRows.Add(row);
            SelectedActivityRow = ActivityRows.FirstOrDefault(
                row => row.RowId == selectedRowId)
                ?? ActivityRows.FirstOrDefault(row => row.NeedsTwoFactor);
            OnPropertyChanged(nameof(EventCount));
            ClearCommand.NotifyCanExecuteChanged();
            if (!string.IsNullOrWhiteSpace(status.Error))
                OperationErrorMessage = status.Error;
            if (status.TargetCount > 0)
            {
                var successCount = status.SuccessCount.ToString("N0", CultureInfo.InvariantCulture);
                var targetCount = status.TargetCount.ToString("N0", CultureInfo.InvariantCulture);
                OperationStatusMessage = status.Running
                    ? string.Format(
                        LocalizationService.Instance["HeroSms.CreatedProgressFormat"],
                        successCount,
                        targetCount,
                        status.ActiveCount.ToString("N0", CultureInfo.InvariantCulture))
                    : status.SuccessCount >= status.TargetCount
                        ? string.Format(
                            LocalizationService.Instance["HeroSms.RegistrationCompleteFormat"],
                            successCount,
                            targetCount)
                        : string.Format(
                            LocalizationService.Instance["HeroSms.RegistrationStoppedFormat"],
                            successCount,
                            targetCount);
            }
        }
        catch (HttpRequestException)
        {
        }
        catch (TaskCanceledException)
        {
        }
    }

    private void RebuildCountryOptions()
    {
        var selectedId = SelectedCountry?.Id;
        Countries.Clear();
        Countries.Add(new HeroSmsCountryOption(
            -1, LocalizationService.Instance["HeroSms.SelectCountryPlaceholder"], IsPlaceholder: true));
        foreach (var country in FilterCountryDtos(_countryDtos))
        {
            var name = LocalizationService.Instance.CurrentLanguage switch
            {
                AppLanguage.Ru => country.RussianName,
                AppLanguage.Zh => country.ChineseName,
                _ => country.EnglishName,
            };
            Countries.Add(new HeroSmsCountryOption(
                country.Id,
                string.IsNullOrWhiteSpace(name) ? country.EnglishName : name));
        }
        SelectedCountry = Countries.FirstOrDefault(option => option.Id == selectedId) ?? Countries[0];
    }

    private IEnumerable<HeroSmsCountryDto> FilterCountryDtos(IEnumerable<HeroSmsCountryDto> countries)
    {
        var query = CountrySearchText.Trim();
        if (string.IsNullOrWhiteSpace(query))
            return countries;

        return countries.Where(country =>
            country.Id.ToString(CultureInfo.InvariantCulture).Contains(query, StringComparison.OrdinalIgnoreCase)
            || country.EnglishName.Contains(query, StringComparison.OrdinalIgnoreCase)
            || country.RussianName.Contains(query, StringComparison.OrdinalIgnoreCase)
            || country.ChineseName.Contains(query, StringComparison.OrdinalIgnoreCase));
    }

    private void UpdateCountriesStatusMessage()
    {
        if (_countryDtos.Count == 0)
        {
            CountriesStatusMessage = "";
            return;
        }

        var shownCount = Math.Max(0, Countries.Count - 1);
        CountriesStatusMessage = string.IsNullOrWhiteSpace(CountrySearchText)
            ? string.Format(LocalizationService.Instance["HeroSms.CountriesLoadedFormat"], _countryDtos.Count)
            : string.Format(
                LocalizationService.Instance["HeroSms.CountriesShownFormat"],
                shownCount,
                _countryDtos.Count);
    }

    private void ResetCountries()
    {
        Countries.Clear();
        Countries.Add(new HeroSmsCountryOption(
            -1, LocalizationService.Instance["HeroSms.SelectCountryPlaceholder"], IsPlaceholder: true));
        SelectedCountry = Countries[0];
    }

    private void ResetOperators()
    {
        Operators.Clear();
        Operators.Add(new HeroSmsOperatorOption(
            "", LocalizationService.Instance["HeroSms.SelectOperatorPlaceholder"], IsPlaceholder: true));
        SelectedOperator = Operators[0];
    }

    private void ResetCatalog()
    {
        PriceOptions.Clear();
        SelectedPriceOption = null;
        CeilingPriceOptions.Clear();
        SelectedCeilingOption = null;
        NumbersAvailable = 0;
        AvailabilityDisplay = FormatAvailability(0);
        CatalogStatusMessage = "";
        CatalogErrorMessage = "";
        StartCommand.NotifyCanExecuteChanged();
    }

    private string FormatAvailability(int value) =>
        _provider.AvailabilityIsPercent
            ? $"{value.ToString("N0", CultureInfo.InvariantCulture)}%"
            : value.ToString("N0", CultureInfo.InvariantCulture);
}
