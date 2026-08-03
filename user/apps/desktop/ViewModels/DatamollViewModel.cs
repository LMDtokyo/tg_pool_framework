using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using TgPoolLauncher.Localization;
using TgPoolLauncher.Models;
using TgPoolLauncher.Services;

namespace TgPoolLauncher.ViewModels;

public partial class DatamollViewModel : ObservableObject
{
    private readonly BackendClient _backend;
    private string? _pendingOrderId;
    private int? _pendingProductId;
    private int _pendingQuantity;
    private readonly List<DatamollProductDto> _allProducts = [];

    public ObservableCollection<DatamollProductDto> Products { get; } = [];
    public ObservableCollection<DatamollActivityRow> ActivityRows { get; } = [];

    [ObservableProperty]
    private string apiKey = "";

    [ObservableProperty]
    private string balanceDisplay = "Not loaded";

    [ObservableProperty]
    private string balanceErrorMessage = "";

    [ObservableProperty]
    private string catalogStatusMessage = LocalizationService.Instance["Datamoll.CatalogStatusLoadPrompt"];

    [ObservableProperty]
    private string catalogErrorMessage = "";

    [ObservableProperty]
    private string countrySearchText = "";

    [ObservableProperty]
    private DatamollProductDto? selectedProduct;

    [ObservableProperty]
    private int quantity = 1;

    [ObservableProperty]
    private string operationStatusMessage = "";

    [ObservableProperty]
    private string operationErrorMessage = "";

    [ObservableProperty]
    private bool isBusy;

    [ObservableProperty]
    private bool isPurchasing;

    public string OrderRangeDisplay => SelectedProduct?.OrderRangeDisplay ?? "-";

    public string TotalDisplay =>
        SelectedProduct is null
            ? "-"
            : $"{SelectedProduct.Currency} {DatamollMoney.Format(SelectedProduct.UnitPrice * Quantity)}";

    public int EventCount => ActivityRows.Count;

    public DatamollViewModel(BackendClient backend)
    {
        _backend = backend;
    }

    partial void OnApiKeyChanged(string value) => RefreshCommandStates();

    partial void OnIsBusyChanged(bool value) => RefreshCommandStates();

    partial void OnIsPurchasingChanged(bool value) => RefreshCommandStates();

    partial void OnCountrySearchTextChanged(string value) => ApplyProductFilter();

    partial void OnSelectedProductChanged(DatamollProductDto? value)
    {
        if (value is not null)
        {
            var maximum = MaximumQuantity(value);
            Quantity = maximum >= value.MinOrder
                ? Math.Clamp(Quantity, value.MinOrder, maximum)
                : value.MinOrder;
        }
        ResetPendingOrder();
        OnPropertyChanged(nameof(OrderRangeDisplay));
        OnPropertyChanged(nameof(TotalDisplay));
        PurchaseCommand.NotifyCanExecuteChanged();
    }

    partial void OnQuantityChanged(int value)
    {
        ResetPendingOrder();
        OnPropertyChanged(nameof(TotalDisplay));
        PurchaseCommand.NotifyCanExecuteChanged();
    }

    private bool CanCallProvider() =>
        !IsBusy
        && !IsPurchasing
        && !string.IsNullOrWhiteSpace(ApiKey);

    private bool CanPurchase()
    {
        if (!CanCallProvider() || SelectedProduct is null)
            return false;
        return Quantity >= SelectedProduct.MinOrder
            && Quantity <= MaximumQuantity(SelectedProduct);
    }

    private static int MaximumQuantity(DatamollProductDto product) =>
        Math.Min(product.Stock, product.MaxOrder ?? product.Stock);

    private void RefreshCommandStates()
    {
        LoadBalanceCommand.NotifyCanExecuteChanged();
        LoadCatalogCommand.NotifyCanExecuteChanged();
        PurchaseCommand.NotifyCanExecuteChanged();
    }

    [RelayCommand(CanExecute = nameof(CanCallProvider))]
    private async Task LoadBalanceAsync()
    {
        IsBusy = true;
        BalanceErrorMessage = "";
        try
        {
            var result = await _backend.GetDatamollBalanceAsync(ApiKey.Trim());
            BalanceDisplay =
                $"{result.Currency} {DatamollMoney.Format(result.AvailableBalance)} available"
                + $"  (balance {DatamollMoney.Format(result.Balance)}, credit {DatamollMoney.Format(result.CreditLimit)})";
        }
        catch (Exception exc)
        {
            BalanceErrorMessage = exc.Message;
        }
        finally
        {
            IsBusy = false;
        }
    }

    [RelayCommand(CanExecute = nameof(CanCallProvider))]
    private async Task LoadCatalogAsync()
    {
        IsBusy = true;
        CatalogErrorMessage = "";
        CatalogStatusMessage = LocalizationService.Instance["Datamoll.CatalogLoading"];
        try
        {
            var result = await _backend.GetDatamollCatalogAsync(ApiKey.Trim());
            _allProducts.Clear();
            _allProducts.AddRange(
                result.Items
                    .OrderBy(item => item.CountryName)
                    .ThenBy(item => item.UnitPrice));
            ApplyProductFilter();
            CatalogStatusMessage = _allProducts.Count == 0
                ? LocalizationService.Instance["Datamoll.CatalogEmpty"]
                : string.Format(
                    LocalizationService.Instance["Datamoll.CatalogShownFormat"],
                    Products.Count,
                    _allProducts.Count);
        }
        catch (Exception exc)
        {
            CatalogStatusMessage = "";
            CatalogErrorMessage = exc.Message;
        }
        finally
        {
            IsBusy = false;
        }
    }

    [RelayCommand(CanExecute = nameof(CanPurchase))]
    private async Task PurchaseAsync()
    {
        var product = SelectedProduct;
        if (product is null)
            return;
        if (_pendingOrderId is null
            || _pendingProductId != product.ProductId
            || _pendingQuantity != Quantity)
        {
            _pendingOrderId =
                $"tgpool-{DateTimeOffset.UtcNow:yyyyMMddHHmmss}-{Guid.NewGuid():N}";
            _pendingProductId = product.ProductId;
            _pendingQuantity = Quantity;
        }

        var externalOrderId = _pendingOrderId;
        var activityRow = ActivityRows.FirstOrDefault(
            row => row.ExternalOrderId == externalOrderId);
        if (activityRow is null)
        {
            activityRow = new DatamollActivityRow(
                DateTimeOffset.Now,
                externalOrderId,
                product.Name,
                Quantity,
                TotalDisplay);
            ActivityRows.Insert(0, activityRow);
            OnPropertyChanged(nameof(EventCount));
        }
        else
        {
            activityRow.OrderId = null;
            activityRow.Total = TotalDisplay;
            activityRow.Status = LocalizationService.Instance["Datamoll.StatusPurchasing"];
            activityRow.Delivered = 0;
            activityRow.Message = "Retrying the same order with Andromeda service...";
            var currentIndex = ActivityRows.IndexOf(activityRow);
            if (currentIndex > 0)
                ActivityRows.Move(currentIndex, 0);
        }

        IsPurchasing = true;
        IsBusy = true;
        OperationErrorMessage = "";
        OperationStatusMessage = "Purchasing and waiting for Andromeda service delivery...";
        try
        {
            var result = await _backend.PurchaseDatamollAccountsAsync(
                new DatamollPurchaseRequest
                {
                    ApiKey = ApiKey.Trim(),
                    ProductId = product.ProductId,
                    Quantity = Quantity,
                    ExternalOrderId = externalOrderId,
                });
            activityRow.OrderId = result.OrderId;
            activityRow.Total = $"{result.Currency} {DatamollMoney.Format(result.TotalAmount)}";
            activityRow.Status = result.ReusedExisting
                ? LocalizationService.Instance["Datamoll.StatusRecovered"]
                : result.Status;
            activityRow.Delivered = result.DeliveredCount;
            activityRow.Message = string.Format(
                LocalizationService.Instance[
                    result.ReusedExisting
                        ? "Datamoll.RecoveredImportedFormat"
                        : "Datamoll.DownloadedImportedFormat"],
                result.ImportedSessions,
                result.ImportedTdata);
            OperationStatusMessage =
                string.Format(
                    LocalizationService.Instance["Datamoll.OrderAddedFormat"],
                    result.OrderId,
                    result.RegisteredAccounts)
                + (result.SkippedExisting > 0
                    ? string.Format(
                        LocalizationService.Instance["Datamoll.SkippedExistingSuffixFormat"],
                        result.SkippedExisting)
                    : ".");
            ResetPendingOrder();
            await LoadBalanceAsync();
            await LoadCatalogAsync();
        }
        catch (Exception exc)
        {
            activityRow.Status = LocalizationService.Instance["Datamoll.StatusFailed"];
            activityRow.Message = exc.Message;
            OperationStatusMessage =
                LocalizationService.Instance["Datamoll.SameOrderWillBeReused"];
            OperationErrorMessage = exc.Message;
        }
        finally
        {
            IsPurchasing = false;
            IsBusy = false;
        }
    }

    [RelayCommand]
    private void Clear()
    {
        ActivityRows.Clear();
        OnPropertyChanged(nameof(EventCount));
        OperationStatusMessage = "";
        OperationErrorMessage = "";
    }

    private void ResetPendingOrder()
    {
        _pendingOrderId = null;
        _pendingProductId = null;
        _pendingQuantity = 0;
    }

    private void ApplyProductFilter()
    {
        var previousSelection = SelectedProduct;
        var search = CountrySearchText.Trim();
        var matches = string.IsNullOrEmpty(search)
            ? _allProducts
            : _allProducts
                .Where(product => product.CountryName.Contains(
                    search,
                    StringComparison.CurrentCultureIgnoreCase))
                .ToList();

        Products.Clear();
        foreach (var product in matches)
            Products.Add(product);

        SelectedProduct = previousSelection is not null && Products.Contains(previousSelection)
            ? previousSelection
            : Products.FirstOrDefault();

        if (_allProducts.Count > 0)
        {
            CatalogStatusMessage = Products.Count == 0
                ? string.Format(LocalizationService.Instance["Datamoll.NoCountriesMatchFormat"], search)
                : string.Format(
                    LocalizationService.Instance["Datamoll.CatalogShownFormat"],
                    Products.Count,
                    _allProducts.Count);
        }
    }
}
