using System.Collections.ObjectModel;
using System.Globalization;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
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
    private string apiSecret = "";

    [ObservableProperty]
    private string balanceDisplay = "Not loaded";

    [ObservableProperty]
    private string balanceErrorMessage = "";

    [ObservableProperty]
    private string catalogStatusMessage = "Load the live catalog to select a Telegram product.";

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

    public string ProductDescription =>
        SelectedProduct?.Description ?? "Select a product to see its delivery description.";

    public string CountryDisplay =>
        SelectedProduct?.CountryName ?? "Not specified";

    public string StockDisplay => SelectedProduct?.Stock.ToString(CultureInfo.InvariantCulture) ?? "-";

    public string AccountAgeDisplay => SelectedProduct?.AccountAge ?? "Not specified";

    public string OrderRangeDisplay => SelectedProduct?.OrderRangeDisplay ?? "-";

    public string UnitPriceDisplay =>
        SelectedProduct is null
            ? "-"
            : $"{SelectedProduct.Currency} {SelectedProduct.Price}";

    public string TotalDisplay =>
        SelectedProduct is null
            ? "-"
            : $"{SelectedProduct.Currency} {(SelectedProduct.UnitPrice * Quantity):0.####}";

    public int EventCount => ActivityRows.Count;

    public DatamollViewModel(BackendClient backend)
    {
        _backend = backend;
    }

    partial void OnApiKeyChanged(string value) => RefreshCommandStates();

    partial void OnApiSecretChanged(string value) => RefreshCommandStates();

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
        OnPropertyChanged(nameof(ProductDescription));
        OnPropertyChanged(nameof(CountryDisplay));
        OnPropertyChanged(nameof(StockDisplay));
        OnPropertyChanged(nameof(AccountAgeDisplay));
        OnPropertyChanged(nameof(OrderRangeDisplay));
        OnPropertyChanged(nameof(UnitPriceDisplay));
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
        && !string.IsNullOrWhiteSpace(ApiKey)
        && !string.IsNullOrWhiteSpace(ApiSecret);

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
            var result = await _backend.GetDatamollBalanceAsync(
                ApiKey.Trim(),
                ApiSecret.Trim());
            BalanceDisplay =
                $"{result.Currency} {result.AvailableBalance} available"
                + $"  (balance {result.Balance}, credit {result.CreditLimit})";
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
        CatalogStatusMessage = "Loading in-stock Telegram products...";
        try
        {
            var result = await _backend.GetDatamollCatalogAsync(
                ApiKey.Trim(),
                ApiSecret.Trim());
            _allProducts.Clear();
            _allProducts.AddRange(
                result.Items
                    .OrderBy(item => item.CountryName)
                    .ThenBy(item => item.UnitPrice));
            ApplyProductFilter();
            CatalogStatusMessage = _allProducts.Count == 0
                ? "No in-stock Telegram products are currently available."
                : $"{Products.Count} of {_allProducts.Count} in-stock Telegram products shown.";
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
            activityRow.Status = "Purchasing";
            activityRow.Delivered = 0;
            activityRow.Message = "Retrying the same order with Datamoll...";
            var currentIndex = ActivityRows.IndexOf(activityRow);
            if (currentIndex > 0)
                ActivityRows.Move(currentIndex, 0);
        }

        IsPurchasing = true;
        IsBusy = true;
        OperationErrorMessage = "";
        OperationStatusMessage = "Purchasing and waiting for Datamoll delivery...";
        try
        {
            var result = await _backend.PurchaseDatamollAccountsAsync(
                new DatamollPurchaseRequest
                {
                    ApiKey = ApiKey.Trim(),
                    ApiSecret = ApiSecret.Trim(),
                    ProductId = product.ProductId,
                    Quantity = Quantity,
                    ExternalOrderId = externalOrderId,
                });
            activityRow.OrderId = result.OrderId;
            activityRow.Total = $"{result.Currency} {result.TotalAmount}";
            activityRow.Status = result.ReusedExisting ? "Recovered" : result.Status;
            activityRow.Delivered = result.DeliveredCount;
            activityRow.Message = result.ReusedExisting
                ? $"Recovered and imported: {result.ImportedSessions} session, {result.ImportedTdata} tdata."
                : $"Downloaded and imported: {result.ImportedSessions} session, {result.ImportedTdata} tdata.";
            OperationStatusMessage =
                $"Order {result.OrderId}: {result.RegisteredAccounts} account(s) added to existing storage"
                + (result.SkippedExisting > 0
                    ? $", {result.SkippedExisting} already existed."
                    : ".");
            ResetPendingOrder();
            await LoadBalanceAsync();
            await LoadCatalogAsync();
        }
        catch (Exception exc)
        {
            activityRow.Status = "Failed";
            activityRow.Message = exc.Message;
            OperationStatusMessage =
                "The same order ID will be reused if you press Purchase again.";
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
                ? $"No countries match \"{search}\"."
                : $"{Products.Count} of {_allProducts.Count} in-stock Telegram products shown.";
        }
    }
}
