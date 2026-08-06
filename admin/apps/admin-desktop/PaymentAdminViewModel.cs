using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Globalization;
using System.Runtime.CompilerServices;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using TgPoolAdmin.Services;

namespace TgPoolAdmin.ViewModels;

public sealed class PaymentAdminViewModel : INotifyPropertyChanged
{
    private readonly AdminApiClient _api;
    private string _adminKey = "";
    private string _searchText = "";
    private string _actor = "launcher-admin";
    private string _selectedSort = "Newest";
    private string _selectedSection = "Dashboard";
    private int _selectedSalesPeriod = 30;
    private string _selectedWithdrawalStatus = "All";
    private AdminUser? _selectedUser;
    private SalesStatistics _salesStatistics = new();
    private DepositStatistics _depositStatistics = new();
    private readonly List<AdminWithdrawal> _allWithdrawals = [];
    private bool _withdrawFullBalance = true;
    private string _withdrawalAmount = "";
    private string _markupPercent = "0";
    private string _markupFixed = "0";
    private string _treasuryAddress = "";
    private string _treasuryNetwork = "";
    private string _treasuryAsset = "";
    private string _treasuryBalance = "";
    private string _treasuryTrxBalance = "";
    private string _datamollAvailableBalance = "";
    private string _datamollCurrency = "USD";
    private bool _hasDatamollBalance;
    private bool _isBusy;
    private string _statusMessage = "";
    private string _errorMessage = "";
    private string _lastTransactionHash = "";

    public PaymentAdminViewModel(AdminApiClient api)
    {
        _api = api;
        LoadCommand = new AsyncCommand(LoadAsync, () => !IsBusy && !string.IsNullOrWhiteSpace(AdminKey));
        RefreshSalesCommand = new AsyncCommand(
            RefreshSalesAsync,
            () => !IsBusy && !string.IsNullOrWhiteSpace(AdminKey));
        LoadPricingCommand = new AsyncCommand(
            LoadPricingAsync,
            () => !IsBusy && !string.IsNullOrWhiteSpace(AdminKey));
        SavePricingCommand = new AsyncCommand(SavePricingAsync, CanSavePricing);
        LoadCatalogPricingCommand = new AsyncCommand(
            LoadCatalogPricingAsync,
            () => !IsBusy && !string.IsNullOrWhiteSpace(AdminKey));
        SaveCountryPricingCommand = new AsyncCommand<CountryPricingRow>(
            SaveCountryPricingAsync, CanSaveCountryPricing);
        ClearCountryOverrideCommand = new AsyncCommand<CountryPricingRow>(
            ClearCountryOverrideAsync, CanClearCountryOverride);
        LoadTreasuryCommand = new AsyncCommand(
            LoadTreasuryAsync,
            () => !IsBusy && !string.IsNullOrWhiteSpace(AdminKey));
        SaveTreasuryCommand = new AsyncCommand(SaveTreasuryAsync, CanSaveTreasury);
        WithdrawCommand = new AsyncCommand(WithdrawAsync, CanWithdraw);
        RefreshWithdrawalCommand = new AsyncCommand<AdminWithdrawal>(
            RefreshWithdrawalAsync,
            withdrawal => !IsBusy && !string.IsNullOrWhiteSpace(AdminKey) && withdrawal?.CanRefresh == true);
    }

    public ObservableCollection<AdminUser> Users { get; } = [];
    public ObservableCollection<AdminWithdrawal> Withdrawals { get; } = [];
    public ObservableCollection<CountryPricingRow> CountryPricing { get; } = [];
    public ObservableCollection<DailyDepositPoint> DailyDeposits { get; } = [];
    public ObservableCollection<DailyDepositPoint> DailyPurchases { get; } = [];
    public ObservableCollection<ChartDateLabel> DailyChartLabels { get; } = [];
    public PointCollection DepositChartPoints { get; private set; } = [];
    public PointCollection DepositChartAreaPoints { get; private set; } = [];
    public PointCollection PurchaseChartPoints { get; private set; } = [];
    public IReadOnlyList<string> SortOptions { get; } =
        ["Newest", "Wallet balance", "Database balance", "Accounts purchased", "Total paid"];
    public IReadOnlyList<int> SalesPeriodOptions { get; } = [7, 30, 90];
    public IReadOnlyList<string> WithdrawalStatusOptions { get; } =
        ["All", "Needs attention", "Submitted", "Confirmed", "Failed"];
    public AsyncCommand LoadCommand { get; }
    public AsyncCommand RefreshSalesCommand { get; }
    public AsyncCommand LoadPricingCommand { get; }
    public AsyncCommand SavePricingCommand { get; }
    public AsyncCommand LoadCatalogPricingCommand { get; }
    public AsyncCommand<CountryPricingRow> SaveCountryPricingCommand { get; }
    public AsyncCommand<CountryPricingRow> ClearCountryOverrideCommand { get; }
    public AsyncCommand LoadTreasuryCommand { get; }
    public AsyncCommand SaveTreasuryCommand { get; }
    public AsyncCommand WithdrawCommand { get; }
    public AsyncCommand<AdminWithdrawal> RefreshWithdrawalCommand { get; }

    public string AdminKey
    {
        get => _adminKey;
        set { if (Set(ref _adminKey, value)) NotifyCommands(); }
    }

    public string SearchText
    {
        get => _searchText;
        set => Set(ref _searchText, value);
    }

    public string Actor
    {
        get => _actor;
        set { if (Set(ref _actor, value)) NotifyCommands(); }
    }

    public string SelectedSort
    {
        get => _selectedSort;
        set
        {
            if (Set(ref _selectedSort, value))
                ApplySort();
        }
    }

    public string SelectedSection
    {
        get => _selectedSection;
        private set
        {
            if (!Set(ref _selectedSection, value))
                return;
            OnPropertyChanged(nameof(IsDashboard));
            OnPropertyChanged(nameof(IsWalletAdmin));
            OnPropertyChanged(nameof(IsPricing));
        }
    }

    public bool IsDashboard => SelectedSection == "Dashboard";
    public bool IsWalletAdmin => SelectedSection == "WalletAdmin";
    public bool IsPricing => SelectedSection == "Pricing";

    public int SelectedSalesPeriod
    {
        get => _selectedSalesPeriod;
        set => Set(ref _selectedSalesPeriod, value);
    }

    public string SelectedWithdrawalStatus
    {
        get => _selectedWithdrawalStatus;
        set
        {
            if (Set(ref _selectedWithdrawalStatus, value))
                ApplyWithdrawalFilter();
        }
    }

    public AdminUser? SelectedUser
    {
        get => _selectedUser;
        set
        {
            if (!Set(ref _selectedUser, value))
                return;
            WithdrawalAmount = "";
            ErrorMessage = "";
            StatusMessage = "";
            LastTransactionHash = "";
            NotifyCommands();
        }
    }

    public bool WithdrawFullBalance
    {
        get => _withdrawFullBalance;
        set
        {
            if (!Set(ref _withdrawFullBalance, value))
                return;
            if (value)
                WithdrawalAmount = "";
            NotifyCommands();
        }
    }

    public string WithdrawalAmount
    {
        get => _withdrawalAmount;
        set { if (Set(ref _withdrawalAmount, value)) NotifyCommands(); }
    }

    public string MarkupPercent
    {
        get => _markupPercent;
        set { if (Set(ref _markupPercent, value)) NotifyCommands(); }
    }

    public string MarkupFixed
    {
        get => _markupFixed;
        set { if (Set(ref _markupFixed, value)) NotifyCommands(); }
    }

    public string TreasuryAddress
    {
        get => _treasuryAddress;
        set { if (Set(ref _treasuryAddress, value)) NotifyCommands(); }
    }

    public string TreasuryNetwork
    {
        get => _treasuryNetwork;
        private set
        {
            if (Set(ref _treasuryNetwork, value))
                OnPropertyChanged(nameof(TreasuryDetails));
        }
    }

    public string TreasuryAsset
    {
        get => _treasuryAsset;
        private set
        {
            if (!Set(ref _treasuryAsset, value))
                return;
            OnPropertyChanged(nameof(TreasuryDetails));
            OnPropertyChanged(nameof(TreasuryBalanceDisplay));
        }
    }

    public string TreasuryBalance
    {
        get => _treasuryBalance;
        private set
        {
            if (!Set(ref _treasuryBalance, value))
                return;
            OnPropertyChanged(nameof(TreasuryBalanceDisplay));
            OnPropertyChanged(nameof(HasTreasuryBalance));
        }
    }

    public string TreasuryTrxBalance
    {
        get => _treasuryTrxBalance;
        private set
        {
            if (!Set(ref _treasuryTrxBalance, value))
                return;
            OnPropertyChanged(nameof(TreasuryTrxBalanceDisplay));
            OnPropertyChanged(nameof(HasTreasuryBalance));
        }
    }

    public bool HasTreasuryBalance =>
        !string.IsNullOrWhiteSpace(TreasuryBalance)
        || !string.IsNullOrWhiteSpace(TreasuryTrxBalance);

    public string TreasuryBalanceDisplay =>
        $"{AdminUser.FormatAmount(TreasuryBalance)} {TreasuryAsset}";

    public string TreasuryTrxBalanceDisplay =>
        $"{AdminUser.FormatAmount(TreasuryTrxBalance)} TRX";

    public string TreasuryDetails => string.IsNullOrWhiteSpace(TreasuryNetwork)
        ? "Destination used for all customer-wallet withdrawals."
        : $"{TreasuryNetwork} · {TreasuryAsset} withdrawal destination";

    // Below this, purchases start failing with "insufficient_balance" at Datamoll --
    // there's no way to top that balance up through their API, only through their
    // own dashboard/support, so this is just an early warning, not something we can
    // resolve in-app.
    private const decimal DatamollLowBalanceThreshold = 10m;

    public string DatamollAvailableBalance
    {
        get => _datamollAvailableBalance;
        private set
        {
            if (!Set(ref _datamollAvailableBalance, value))
                return;
            OnPropertyChanged(nameof(DatamollBalanceDisplay));
            OnPropertyChanged(nameof(IsDatamollBalanceLow));
        }
    }

    public string DatamollCurrency
    {
        get => _datamollCurrency;
        private set
        {
            if (!Set(ref _datamollCurrency, value))
                return;
            OnPropertyChanged(nameof(DatamollBalanceDisplay));
        }
    }

    public bool HasDatamollBalance
    {
        get => _hasDatamollBalance;
        private set => Set(ref _hasDatamollBalance, value);
    }

    public string DatamollBalanceDisplay =>
        $"{AdminUser.FormatAmount(DatamollAvailableBalance)} {DatamollCurrency}";

    public bool IsDatamollBalanceLow =>
        HasDatamollBalance
        && decimal.TryParse(
            DatamollAvailableBalance, NumberStyles.Number, CultureInfo.InvariantCulture, out var amount)
        && amount < DatamollLowBalanceThreshold;

    public bool IsBusy
    {
        get => _isBusy;
        private set
        {
            if (Set(ref _isBusy, value))
                NotifyCommands();
        }
    }

    public string StatusMessage
    {
        get => _statusMessage;
        private set => Set(ref _statusMessage, value);
    }

    public string ErrorMessage
    {
        get => _errorMessage;
        private set => Set(ref _errorMessage, value);
    }

    public string LastTransactionHash
    {
        get => _lastTransactionHash;
        private set => Set(ref _lastTransactionHash, value);
    }

    public int UserCount => Users.Count;
    public int WithdrawalCount => Withdrawals.Count;
    public string TodayGrossDisplay => MoneyDisplay(SalesStatistics.Today.GrossSales);
    public string PeriodGrossDisplay => MoneyDisplay(SalesStatistics.Period.GrossSales);
    public string AllTimeGrossDisplay => MoneyDisplay(SalesStatistics.AllTime.GrossSales);
    public string TodayDepositedDisplay => DepositMoneyDisplay(_depositStatistics.Today.TotalDeposited);
    public string PeriodDepositedDisplay => DepositMoneyDisplay(_depositStatistics.Period.TotalDeposited);
    public string AllTimeDepositedDisplay => DepositMoneyDisplay(_depositStatistics.AllTime.TotalDeposited);
    public int PeriodCompletedOrders => SalesStatistics.Period.CompletedOrders;
    public int PeriodAccountsSold => SalesStatistics.Period.AccountsSold;
    public string PeriodLabel => $"Last {SalesStatistics.Days} days";

    private SalesStatistics SalesStatistics
    {
        get => _salesStatistics;
        set
        {
            _salesStatistics = value;
            OnPropertyChanged(nameof(TodayGrossDisplay));
            OnPropertyChanged(nameof(PeriodGrossDisplay));
            OnPropertyChanged(nameof(AllTimeGrossDisplay));
            OnPropertyChanged(nameof(PeriodCompletedOrders));
            OnPropertyChanged(nameof(PeriodAccountsSold));
            OnPropertyChanged(nameof(PeriodLabel));
        }
    }

    public void SelectSection(string section)
    {
        if (section is "Dashboard" or "WalletAdmin" or "Pricing")
            SelectedSection = section;
    }

    public void PrepareWithdrawal(AdminUser user)
    {
        SelectedUser = user;
        WithdrawFullBalance = true;
        WithdrawalAmount = "";
    }

    private async Task LoadAsync()
    {
        IsBusy = true;
        ErrorMessage = "";
        StatusMessage = "Loading sales, withdrawals, and live wallet balances...";
        try
        {
            var key = AdminKey.Trim();
            var usersTask = _api.GetUsersAsync(key, SearchText.Trim());
            var salesTask = _api.GetSalesStatisticsAsync(key, SelectedSalesPeriod);
            var depositsTask = _api.GetDepositStatisticsAsync(key, SelectedSalesPeriod);
            await Task.WhenAll(usersTask, salesTask, depositsTask);

            ReplaceUsers((await usersTask).Items);
            SetSalesStatistics(await salesTask);
            SetDepositStatistics(await depositsTask);
            StatusMessage = $"Loaded {Users.Count} user wallets.";
        }
        catch (Exception exception)
        {
            StatusMessage = "";
            ErrorMessage = exception.Message;
        }
        finally
        {
            IsBusy = false;
        }
    }

    private async Task RefreshUsersAsync()
    {
        var selectedId = SelectedUser?.UserId;
        var response = await _api.GetUsersAsync(AdminKey.Trim(), SearchText.Trim());
        ReplaceUsers(response.Items, selectedId);
    }

    private async Task RefreshSalesAsync()
    {
        IsBusy = true;
        ErrorMessage = "";
        StatusMessage = $"Loading {SelectedSalesPeriod}-day sales and deposit statistics...";
        try
        {
            var key = AdminKey.Trim();
            var salesTask = _api.GetSalesStatisticsAsync(key, SelectedSalesPeriod);
            var depositsTask = _api.GetDepositStatisticsAsync(key, SelectedSalesPeriod);
            await Task.WhenAll(salesTask, depositsTask);
            SetSalesStatistics(await salesTask);
            SetDepositStatistics(await depositsTask);
            StatusMessage = $"Loaded {SelectedSalesPeriod}-day dashboard statistics.";
        }
        catch (Exception exception)
        {
            StatusMessage = "";
            ErrorMessage = exception.Message;
        }
        finally
        {
            IsBusy = false;
        }
    }

    private async Task LoadPricingAsync()
    {
        IsBusy = true;
        ErrorMessage = "";
        StatusMessage = "Loading retail markup settings...";
        try
        {
            var pricing = await _api.GetPricingAsync(AdminKey.Trim());
            ApplyPricing(pricing);
            StatusMessage = "Loaded retail markup settings.";
        }
        catch (Exception exception)
        {
            StatusMessage = "";
            ErrorMessage = exception.Message;
        }
        finally
        {
            IsBusy = false;
        }
    }

    private bool CanSavePricing() =>
        !IsBusy
        && !string.IsNullOrWhiteSpace(AdminKey)
        && decimal.TryParse(
            MarkupPercent.Trim(),
            NumberStyles.Number,
            CultureInfo.InvariantCulture,
            out var percent)
        && percent >= 0
        && decimal.TryParse(
            MarkupFixed.Trim(),
            NumberStyles.Number,
            CultureInfo.InvariantCulture,
            out var fixedAmount)
        && fixedAmount >= 0;

    private async Task SavePricingAsync()
    {
        IsBusy = true;
        ErrorMessage = "";
        StatusMessage = "Saving retail markup settings...";
        try
        {
            var pricing = await _api.UpdatePricingAsync(
                AdminKey.Trim(),
                MarkupPercent.Trim(),
                MarkupFixed.Trim());
            ApplyPricing(pricing);
            StatusMessage =
                $"Saved markup: {AdminUser.FormatAmount(pricing.MarkupPercent)}% + "
                + $"{AdminUser.FormatAmount(pricing.MarkupFixed)} fixed.";
        }
        catch (Exception exception)
        {
            StatusMessage = "";
            ErrorMessage = exception.Message;
        }
        finally
        {
            IsBusy = false;
        }
    }

    private void ApplyPricing(RetailPricing pricing)
    {
        MarkupPercent = AdminUser.FormatAmount(pricing.MarkupPercent);
        MarkupFixed = AdminUser.FormatAmount(pricing.MarkupFixed);
    }

    private async Task LoadCatalogPricingAsync()
    {
        IsBusy = true;
        ErrorMessage = "";
        StatusMessage = "Loading the catalog and country markup overrides...";
        try
        {
            var key = AdminKey.Trim();
            var catalogTask = _api.GetCatalogAsync(key);
            var overridesTask = _api.GetCountryPricingAsync(key);
            var balanceTask = _api.GetDatamollBalanceAsync(key);
            await Task.WhenAll(catalogTask, overridesTask, balanceTask);
            ApplyDatamollBalance(await balanceTask);
            var catalog = (await catalogTask).Items;
            var overrides = (await overridesTask).Items
                .ToDictionary(item => item.Country, item => item);

            var grouped = catalog
                .GroupBy(item => string.IsNullOrWhiteSpace(item.Country)
                    ? "—"
                    : item.Country.Trim().ToUpperInvariant())
                .OrderBy(group => group.Key);

            CountryPricing.Clear();
            foreach (var group in grouped)
            {
                var hasOverride = overrides.TryGetValue(group.Key, out var over);
                CountryPricing.Add(new CountryPricingRow
                {
                    Country = group.Key,
                    ItemCount = group.Count(),
                    WholesaleRangeDisplay = FormatRange(group.Select(item => item.WholesaleValue)),
                    RetailRangeDisplay = FormatRange(
                        group.Select(item => ParseAmount(item.RetailPrice))),
                    HasOverride = hasOverride,
                    MarkupPercent = hasOverride ? AdminUser.FormatAmount(over!.MarkupPercent) : "",
                    MarkupFixed = hasOverride ? AdminUser.FormatAmount(over!.MarkupFixed) : "",
                });
            }
            StatusMessage = $"Loaded {CountryPricing.Count} countries from the catalog.";
        }
        catch (Exception exception)
        {
            StatusMessage = "";
            ErrorMessage = exception.Message;
        }
        finally
        {
            IsBusy = false;
        }
    }

    private bool CanSaveCountryPricing(CountryPricingRow? row) =>
        !IsBusy
        && row is not null
        && !string.IsNullOrWhiteSpace(AdminKey)
        && decimal.TryParse(
            row.MarkupPercent, NumberStyles.Number, CultureInfo.InvariantCulture, out var percent)
        && percent >= 0
        && decimal.TryParse(
            row.MarkupFixed, NumberStyles.Number, CultureInfo.InvariantCulture, out var fixedAmount)
        && fixedAmount >= 0;

    private async Task SaveCountryPricingAsync(CountryPricingRow? row)
    {
        if (row is null)
            return;
        IsBusy = true;
        ErrorMessage = "";
        StatusMessage = $"Saving the markup for {row.Country}...";
        try
        {
            var saved = await _api.SaveCountryPricingAsync(
                AdminKey.Trim(), row.Country, row.MarkupPercent.Trim(), row.MarkupFixed.Trim());
            row.MarkupPercent = AdminUser.FormatAmount(saved.MarkupPercent);
            row.MarkupFixed = AdminUser.FormatAmount(saved.MarkupFixed);
            row.HasOverride = true;
            StatusMessage = $"Saved the {row.Country} markup: "
                + $"{AdminUser.FormatAmount(saved.MarkupPercent)}% + "
                + $"{AdminUser.FormatAmount(saved.MarkupFixed)} fixed.";
        }
        catch (Exception exception)
        {
            StatusMessage = "";
            ErrorMessage = exception.Message;
        }
        finally
        {
            IsBusy = false;
            NotifyCommands();
        }
    }

    private bool CanClearCountryOverride(CountryPricingRow? row) =>
        !IsBusy && row is { HasOverride: true } && !string.IsNullOrWhiteSpace(AdminKey);

    private async Task ClearCountryOverrideAsync(CountryPricingRow? row)
    {
        if (row is null)
            return;
        IsBusy = true;
        ErrorMessage = "";
        StatusMessage = $"Clearing the markup override for {row.Country}...";
        try
        {
            await _api.DeleteCountryPricingAsync(AdminKey.Trim(), row.Country);
            row.MarkupPercent = "";
            row.MarkupFixed = "";
            row.HasOverride = false;
            StatusMessage = $"{row.Country} now uses the global default markup.";
        }
        catch (Exception exception)
        {
            StatusMessage = "";
            ErrorMessage = exception.Message;
        }
        finally
        {
            IsBusy = false;
            NotifyCommands();
        }
    }

    private static string FormatRange(IEnumerable<decimal> values)
    {
        var list = values.ToList();
        if (list.Count == 0)
            return "—";
        var min = list.Min();
        var max = list.Max();
        return min == max
            ? min.ToString("0.##", CultureInfo.InvariantCulture)
            : $"{min.ToString("0.##", CultureInfo.InvariantCulture)}"
                + $"–{max.ToString("0.##", CultureInfo.InvariantCulture)}";
    }

    private async Task LoadTreasuryAsync()
    {
        IsBusy = true;
        ErrorMessage = "";
        StatusMessage = "Loading administrator wallet...";
        try
        {
            ApplyTreasury(await _api.GetTreasuryWalletAsync(AdminKey.Trim()));
            StatusMessage = "Loaded the administrator wallet.";
        }
        catch (Exception exception)
        {
            StatusMessage = "";
            ErrorMessage = exception.Message;
        }
        finally
        {
            IsBusy = false;
        }
    }

    private bool CanSaveTreasury() =>
        !IsBusy
        && !string.IsNullOrWhiteSpace(AdminKey)
        && TreasuryAddress.Trim().Length is >= 34 and <= 64;

    private async Task SaveTreasuryAsync()
    {
        var address = TreasuryAddress.Trim();
        var answer = MessageBox.Show(
            $"Change the administrator wallet to:\n\n{address}\n\n"
            + "All future customer-wallet withdrawals will be sent to this address.",
            "Change administrator wallet",
            MessageBoxButton.YesNo,
            MessageBoxImage.Warning);
        if (answer != MessageBoxResult.Yes)
            return;

        IsBusy = true;
        ErrorMessage = "";
        StatusMessage = "Changing administrator wallet...";
        try
        {
            ApplyTreasury(await _api.UpdateTreasuryWalletAsync(AdminKey.Trim(), address));
            StatusMessage = "Administrator wallet changed successfully.";
        }
        catch (Exception exception)
        {
            StatusMessage = "";
            ErrorMessage = exception.Message;
        }
        finally
        {
            IsBusy = false;
        }
    }

    private void ApplyDatamollBalance(ProviderBalance balance)
    {
        DatamollAvailableBalance = balance.AvailableBalance;
        DatamollCurrency = balance.Currency;
        HasDatamollBalance = true;
    }

    private void ApplyTreasury(TreasuryWallet wallet)
    {
        TreasuryAddress = wallet.Address;
        TreasuryNetwork = wallet.Network;
        TreasuryAsset = wallet.Asset;
        TreasuryBalance = wallet.OnChainBalance;
        TreasuryTrxBalance = wallet.TrxBalance;
    }

    private void ReplaceUsers(IEnumerable<AdminUser> users, int? selectedId = null)
    {
        selectedId ??= SelectedUser?.UserId;
        Users.Clear();
        foreach (var user in Sorted(users))
            Users.Add(user);
        SelectedUser = selectedId is null
            ? null
            : Users.FirstOrDefault(user => user.UserId == selectedId);
        OnPropertyChanged(nameof(UserCount));
    }

    private void SetSalesStatistics(SalesStatistics statistics)
    {
        SalesStatistics = statistics;
        UpdateFinancialChart();
    }

    private void SetDepositStatistics(DepositStatistics statistics)
    {
        _depositStatistics = statistics;
        OnPropertyChanged(nameof(TodayDepositedDisplay));
        OnPropertyChanged(nameof(PeriodDepositedDisplay));
        OnPropertyChanged(nameof(AllTimeDepositedDisplay));
        UpdateFinancialChart();
    }

    private void UpdateFinancialChart()
    {
        DailyDeposits.Clear();
        DailyPurchases.Clear();
        DailyChartLabels.Clear();
        var maximum = _depositStatistics.Daily
            .Select(day => ParseAmount(day.TotalDeposited))
            .Concat(SalesStatistics.Daily.Select(day => ParseAmount(day.GrossSales)))
            .DefaultIfEmpty(0)
            .Max();
        const double chartWidth = 1000;
        const double horizontalPadding = 45;
        const double plotWidth = chartWidth - horizontalPadding * 2;
        var dayCount = Math.Max(_depositStatistics.Daily.Count, SalesStatistics.Daily.Count);
        var slotWidth = dayCount == 0
            ? plotWidth
            : plotWidth / dayCount;
        var labelStep = Math.Max(1, (int)Math.Ceiling(dayCount / 8d));
        var depositPoints = new PointCollection();
        foreach (var (day, index) in _depositStatistics.Daily.Select((day, index) => (day, index)))
        {
            var value = ParseAmount(day.TotalDeposited);
            var x = horizontalPadding + index * slotWidth + slotWidth / 2;
            var y = maximum <= 0 ? 250 : 250 - (double)(value / maximum) * 225;
            depositPoints.Add(new Point(x, y));
            if (index % labelStep == 0 || index == _depositStatistics.Daily.Count - 1)
                DailyChartLabels.Add(new ChartDateLabel(day.Date, x - 45));
            DailyDeposits.Add(new DailyDepositPoint(
                day.Date,
                $"{AdminUser.FormatAmount(day.TotalDeposited)} {_depositStatistics.Asset} deposited",
                day.DepositCount,
                x - 4,
                y - 4));
        }
        var purchasePoints = new PointCollection();
        foreach (var (day, index) in SalesStatistics.Daily.Select((day, index) => (day, index)))
        {
            var value = ParseAmount(day.GrossSales);
            var x = horizontalPadding + index * slotWidth + slotWidth / 2;
            var y = maximum <= 0 ? 250 : 250 - (double)(value / maximum) * 225;
            purchasePoints.Add(new Point(x, y));
            DailyPurchases.Add(new DailyDepositPoint(
                day.Date,
                $"{AdminUser.FormatAmount(day.GrossSales)} {SalesStatistics.Currency} purchased",
                day.CompletedOrders,
                x - 4,
                y - 4));
        }
        DepositChartPoints = depositPoints;
        DepositChartAreaPoints = depositPoints.Count == 0
            ? []
            : [
                new Point(depositPoints[0].X, 258),
                .. depositPoints,
                new Point(depositPoints[^1].X, 258),
            ];
        PurchaseChartPoints = purchasePoints;
        OnPropertyChanged(nameof(DepositChartPoints));
        OnPropertyChanged(nameof(DepositChartAreaPoints));
        OnPropertyChanged(nameof(PurchaseChartPoints));
    }

    private void ReplaceWithdrawals(IEnumerable<AdminWithdrawal> withdrawals)
    {
        _allWithdrawals.Clear();
        _allWithdrawals.AddRange(withdrawals.OrderByDescending(item => item.CreatedAt));
        ApplyWithdrawalFilter();
    }

    private void ApplyWithdrawalFilter()
    {
        IEnumerable<AdminWithdrawal> filtered = _allWithdrawals;
        filtered = SelectedWithdrawalStatus switch
        {
            "Needs attention" => filtered.Where(item => item.Status is "created" or "review_required"),
            "Submitted" => filtered.Where(item => item.Status == "submitted"),
            "Confirmed" => filtered.Where(item => item.Status == "confirmed"),
            "Failed" => filtered.Where(item => item.Status == "failed"),
            _ => filtered,
        };
        Withdrawals.Clear();
        foreach (var withdrawal in filtered)
            Withdrawals.Add(withdrawal);
        OnPropertyChanged(nameof(WithdrawalCount));
    }

    private bool CanWithdraw()
    {
        if (IsBusy || SelectedUser is null || string.IsNullOrWhiteSpace(AdminKey)
            || string.IsNullOrWhiteSpace(Actor) || SelectedUser.OnChainValue <= 0)
            return false;
        if (WithdrawFullBalance)
            return true;
        return decimal.TryParse(
                WithdrawalAmount,
                NumberStyles.Number,
                CultureInfo.InvariantCulture,
                out var amount)
            && amount > 0
            && amount <= SelectedUser.OnChainValue;
    }

    private async Task WithdrawAsync()
    {
        var user = SelectedUser;
        if (user is null)
            return;
        var displayAmount = WithdrawFullBalance ? user.OnChainBalance ?? "0" : WithdrawalAmount.Trim();
        var answer = MessageBox.Show(
            $"Withdraw {displayAmount} {user.Asset} from {user.UsernameDisplay}?\n\n"
            + $"Source: {user.Address}\n\nFunds can only be sent to the configured treasury. "
            + "The database purchasing balance will remain unchanged.",
            "Withdraw wallet funds",
            MessageBoxButton.YesNo,
            MessageBoxImage.Warning);
        if (answer != MessageBoxResult.Yes)
            return;

        IsBusy = true;
        ErrorMessage = "";
        LastTransactionHash = "";
        StatusMessage = "Submitting withdrawal through the signer...";
        try
        {
            var result = await _api.CreateWithdrawalAsync(
                user.UserId,
                AdminKey.Trim(),
                Actor.Trim(),
                $"tgpool-admin-{Guid.NewGuid():N}",
                WithdrawFullBalance ? null : WithdrawalAmount.Trim());
            var success = $"Withdrawal {result.Status}: "
                          + $"{result.TransferredAmount ?? result.RequestedAmount} {result.Asset}.";
            await RefreshUsersAsync();
            LastTransactionHash = result.TransactionHash ?? "";
            StatusMessage = success;
            ErrorMessage = result.ErrorMessage;
        }
        catch (Exception exception)
        {
            StatusMessage = "Refresh wallet balances before retrying this withdrawal.";
            ErrorMessage = exception.Message;
        }
        finally
        {
            IsBusy = false;
        }
    }

    private async Task RefreshWithdrawalAsync(AdminWithdrawal? withdrawal)
    {
        if (withdrawal is null)
            return;
        IsBusy = true;
        ErrorMessage = "";
        StatusMessage = $"Refreshing withdrawal #{withdrawal.Id}...";
        try
        {
            var refreshed = await _api.RefreshWithdrawalAsync(withdrawal.Id, AdminKey.Trim());
            var index = _allWithdrawals.FindIndex(item => item.Id == refreshed.Id);
            if (index >= 0)
                _allWithdrawals[index] = refreshed;
            else
                _allWithdrawals.Add(refreshed);
            ApplyWithdrawalFilter();
            StatusMessage = $"Withdrawal #{refreshed.Id} is {refreshed.Status}.";
            ErrorMessage = refreshed.ErrorMessage;
        }
        catch (Exception exception)
        {
            StatusMessage = "";
            ErrorMessage = exception.Message;
        }
        finally
        {
            IsBusy = false;
        }
    }

    private IEnumerable<AdminUser> Sorted(IEnumerable<AdminUser> users) => SelectedSort switch
    {
        "Wallet balance" => users.OrderByDescending(user => user.OnChainValue),
        "Database balance" => users.OrderByDescending(user => user.DatabaseValue),
        "Accounts purchased" => users.OrderByDescending(user => user.TotalAccountsPurchased),
        "Total paid" => users.OrderByDescending(user => user.TotalPaidValue),
        _ => users.OrderByDescending(user => user.UserId),
    };

    private void ApplySort()
    {
        var sorted = Sorted(Users).ToList();
        Users.Clear();
        foreach (var user in sorted)
            Users.Add(user);
    }

    private void NotifyCommands()
    {
        LoadCommand.RaiseCanExecuteChanged();
        RefreshSalesCommand.RaiseCanExecuteChanged();
        LoadPricingCommand.RaiseCanExecuteChanged();
        SavePricingCommand.RaiseCanExecuteChanged();
        LoadCatalogPricingCommand.RaiseCanExecuteChanged();
        SaveCountryPricingCommand.RaiseCanExecuteChanged();
        ClearCountryOverrideCommand.RaiseCanExecuteChanged();
        LoadTreasuryCommand.RaiseCanExecuteChanged();
        SaveTreasuryCommand.RaiseCanExecuteChanged();
        WithdrawCommand.RaiseCanExecuteChanged();
        RefreshWithdrawalCommand.RaiseCanExecuteChanged();
    }

    private string MoneyDisplay(string value) =>
        $"{AdminUser.FormatAmount(value)} {SalesStatistics.Currency}";

    private string DepositMoneyDisplay(string value) =>
        $"{AdminUser.FormatAmount(value)} {_depositStatistics.Asset}";

    private static decimal ParseAmount(string? value) =>
        decimal.TryParse(value, NumberStyles.Number, CultureInfo.InvariantCulture, out var amount)
            ? amount
            : 0;

    private bool Set<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value))
            return false;
        field = value;
        OnPropertyChanged(propertyName);
        return true;
    }

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));

    public event PropertyChangedEventHandler? PropertyChanged;
}

public sealed record DailyDepositPoint(
    string Date,
    string AmountDisplay,
    int DepositCount,
    double PointLeft,
    double PointTop);

public sealed record ChartDateLabel(string Date, double PointLeft);

public sealed class CountryPricingRow : INotifyPropertyChanged
{
    private string _markupPercent = "";
    private string _markupFixed = "";
    private bool _hasOverride;

    public required string Country { get; init; }
    public int ItemCount { get; init; }
    public string WholesaleRangeDisplay { get; init; } = "—";
    public string RetailRangeDisplay { get; init; } = "—";

    public bool HasOverride
    {
        get => _hasOverride;
        set => Set(ref _hasOverride, value);
    }

    public string MarkupPercent
    {
        get => _markupPercent;
        set => Set(ref _markupPercent, value);
    }

    public string MarkupFixed
    {
        get => _markupFixed;
        set => Set(ref _markupFixed, value);
    }

    private bool Set<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value))
            return false;
        field = value;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
        return true;
    }

    public event PropertyChangedEventHandler? PropertyChanged;
}

public sealed class AsyncCommand : ICommand
{
    private readonly Func<Task> _execute;
    private readonly Func<bool> _canExecute;
    private bool _executing;

    public AsyncCommand(Func<Task> execute, Func<bool> canExecute)
    {
        _execute = execute;
        _canExecute = canExecute;
    }

    public bool CanExecute(object? parameter) => !_executing && _canExecute();

    public async void Execute(object? parameter)
    {
        if (!CanExecute(parameter))
            return;
        _executing = true;
        RaiseCanExecuteChanged();
        try
        {
            await _execute();
        }
        finally
        {
            _executing = false;
            RaiseCanExecuteChanged();
        }
    }

    public void RaiseCanExecuteChanged() => CanExecuteChanged?.Invoke(this, EventArgs.Empty);

    public event EventHandler? CanExecuteChanged;
}

public sealed class AsyncCommand<T> : ICommand
{
    private readonly Func<T?, Task> _execute;
    private readonly Func<T?, bool> _canExecute;
    private bool _executing;

    public AsyncCommand(Func<T?, Task> execute, Func<T?, bool> canExecute)
    {
        _execute = execute;
        _canExecute = canExecute;
    }

    public bool CanExecute(object? parameter) =>
        !_executing && _canExecute(parameter is T value ? value : default);

    public async void Execute(object? parameter)
    {
        var value = parameter is T typed ? typed : default;
        if (!CanExecute(parameter))
            return;
        _executing = true;
        RaiseCanExecuteChanged();
        try
        {
            await _execute(value);
        }
        finally
        {
            _executing = false;
            RaiseCanExecuteChanged();
        }
    }

    public void RaiseCanExecuteChanged() => CanExecuteChanged?.Invoke(this, EventArgs.Empty);

    public event EventHandler? CanExecuteChanged;
}
