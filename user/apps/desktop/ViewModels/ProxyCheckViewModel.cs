using System.Collections.ObjectModel;
using System.Net.Http;
using System.Windows;
using System.Windows.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using TgPoolLauncher.Localization;
using TgPoolLauncher.Models;
using TgPoolLauncher.Services;

namespace TgPoolLauncher.ViewModels;

public partial class ProxyCheckViewModel : ObservableObject
{
    private readonly BackendClient _backend;
    private readonly DispatcherTimer _statusTimer;
    private bool _isRefreshing;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(AddCommand))]
    private string proxyListText = "";

    [ObservableProperty]
    private string selectedProtocol = "HTTP";

    [ObservableProperty]
    private StoredProxyCheckStatusDto? latestStatus;

    [ObservableProperty]
    private string statusMessage = "";

    [ObservableProperty]
    private double checkTimeout = 10;

    [ObservableProperty]
    private int retryAttempts = 2;

    public bool IsRunning => LatestStatus?.Running == true;
    public bool HasProxies => Proxies.Count > 0;
    public bool HasBadProxies => Proxies.Any(proxy => proxy.Status == "bad");

    public IReadOnlyList<string> Protocols { get; } = ["HTTP", "SOCKS5"];
    public ObservableCollection<StoredProxyDto> Proxies { get; } = new();

    public ProxyCheckViewModel(BackendClient backend)
    {
        _backend = backend;
        _statusTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1.5) };
        _statusTimer.Tick += async (_, _) => await RefreshAsync();
        _ = RefreshAsync();
    }

    partial void OnLatestStatusChanged(StoredProxyCheckStatusDto? value)
    {
        OnPropertyChanged(nameof(IsRunning));
        NotifyCommandStates();
        if (value?.Running == true)
            _statusTimer.Start();
        else
            _statusTimer.Stop();
        if (!string.IsNullOrWhiteSpace(value?.Error))
            StatusMessage = value.Error;
    }

    private async Task RefreshAsync()
    {
        if (_isRefreshing)
            return;
        _isRefreshing = true;
        try
        {
            LatestStatus = await _backend.GetStoredProxyCheckStatusAsync();
            ReplaceProxies(await _backend.GetStoredProxiesAsync());
        }
        catch (HttpRequestException)
        {
            // Keep the last visible list while the local backend restarts.
        }
        catch (TaskCanceledException)
        {
            // Keep the last visible list when a polling request is cancelled.
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
        finally
        {
            _isRefreshing = false;
        }
    }

    private void ReplaceProxies(IEnumerable<StoredProxyDto> proxies)
    {
        Proxies.Clear();
        foreach (var proxy in proxies)
            Proxies.Add(proxy);
        OnPropertyChanged(nameof(HasProxies));
        OnPropertyChanged(nameof(HasBadProxies));
        NotifyCommandStates();
    }

    [RelayCommand(CanExecute = nameof(CanAdd))]
    private async Task AddAsync()
    {
        StatusMessage = "";
        try
        {
            var proxies = await _backend.AddStoredProxiesAsync(new ProxyBulkCreateRequest
            {
                Protocol = SelectedProtocol.ToLowerInvariant(),
                ProxyList = ProxyListText,
            });
            ProxyListText = "";
            ReplaceProxies(proxies);
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }

    private bool CanAdd() => !IsRunning && !string.IsNullOrWhiteSpace(ProxyListText);

    [RelayCommand(CanExecute = nameof(CanCheckAll))]
    private async Task CheckAllAsync() => await StartCheckAsync(null);

    private bool CanCheckAll() => !IsRunning && HasProxies;

    [RelayCommand(CanExecute = nameof(CanCheckProxy))]
    private async Task CheckProxyAsync(StoredProxyDto? proxy)
    {
        if (proxy is not null)
            await StartCheckAsync([proxy.Id]);
    }

    private bool CanCheckProxy(StoredProxyDto? proxy) => !IsRunning && proxy is not null;

    private async Task StartCheckAsync(List<int>? proxyIds)
    {
        StatusMessage = "";
        try
        {
            await _backend.StartStoredProxyCheckAsync(new StoredProxyCheckRequest
            {
                ProxyIds = proxyIds,
                Timeout = Math.Clamp(CheckTimeout, 1, 45),
                Retries = Math.Clamp(RetryAttempts, 0, 15),
            });
            await RefreshAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }

    [RelayCommand(CanExecute = nameof(CanDeleteProxy))]
    private async Task DeleteProxyAsync(StoredProxyDto? proxy)
    {
        if (proxy is null)
            return;
        try
        {
            await _backend.DeleteStoredProxyAsync(proxy.Id);
            await RefreshAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }

    private bool CanDeleteProxy(StoredProxyDto? proxy) => !IsRunning && proxy is not null;

    [RelayCommand(CanExecute = nameof(CanDeleteBad))]
    private async Task DeleteBadAsync()
    {
        try
        {
            await _backend.DeleteBadStoredProxiesAsync();
            await RefreshAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }

    private bool CanDeleteBad() => !IsRunning && HasBadProxies;

    [RelayCommand(CanExecute = nameof(CanDeleteAll))]
    private async Task DeleteAllAsync()
    {
        var answer = MessageBox.Show(
            LocalizationService.Instance["Proxy.DeleteAllConfirm"],
            LocalizationService.Instance["Proxy.DeleteAll"],
            MessageBoxButton.YesNo,
            MessageBoxImage.Warning);
        if (answer != MessageBoxResult.Yes)
            return;

        try
        {
            await _backend.DeleteAllStoredProxiesAsync();
            await RefreshAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }

    private bool CanDeleteAll() => !IsRunning && HasProxies;

    private void NotifyCommandStates()
    {
        AddCommand.NotifyCanExecuteChanged();
        CheckAllCommand.NotifyCanExecuteChanged();
        CheckProxyCommand.NotifyCanExecuteChanged();
        DeleteProxyCommand.NotifyCanExecuteChanged();
        DeleteBadCommand.NotifyCanExecuteChanged();
        DeleteAllCommand.NotifyCanExecuteChanged();
    }
}
