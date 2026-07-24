using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using System.Globalization;
using System.Net.Http;
using System.Windows.Threading;
using TgPoolLauncher.Localization;
using TgPoolLauncher.Models;
using TgPoolLauncher.Services;

namespace TgPoolLauncher.ViewModels;

/// <summary>
/// Proxy-pool quality check: sends real IP-service requests through rotating or
/// sticky proxies and tallies unique exit IPs, duplicates, and connection errors.
/// </summary>
public partial class ProxyPoolCheckerViewModel : ObservableObject
{
    private readonly BackendClient _backend;
    private readonly DispatcherTimer _statusTimer;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private int rotationModeIndex;

    public bool IsRotatingMode => RotationModeIndex == 0;

    public bool IsStickyMode => RotationModeIndex == 1;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private int rotationProtocolIndex;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string rotationProxyText = "";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string rotationRequestCount = "0";

    [ObservableProperty]
    private int rotationUniqueCount;

    [ObservableProperty]
    private int rotationDuplicateCount;

    [ObservableProperty]
    private int rotationErrorCount;

    [ObservableProperty]
    private string statusMessage = "";

    [ObservableProperty]
    private ProxyPoolCheckStatusDto? latestStatus;

    public bool IsRunning => LatestStatus?.Running == true;

    public ProxyPoolCheckerViewModel(BackendClient backend)
    {
        _backend = backend;
        _statusTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1.5) };
        _statusTimer.Tick += async (_, _) => await RefreshStatusAsync();
        _statusTimer.Start();
    }

    [RelayCommand]
    private void ResetForm()
    {
        RotationModeIndex = 0;
        RotationProtocolIndex = 0;
        RotationProxyText = "";
        RotationRequestCount = "0";
        RotationUniqueCount = 0;
        RotationDuplicateCount = 0;
        RotationErrorCount = 0;
        StatusMessage = "";
    }

    partial void OnRotationModeIndexChanged(int value)
    {
        OnPropertyChanged(nameof(IsRotatingMode));
        OnPropertyChanged(nameof(IsStickyMode));
    }

    partial void OnLatestStatusChanged(ProxyPoolCheckStatusDto? value)
    {
        OnPropertyChanged(nameof(IsRunning));
        StartCommand.NotifyCanExecuteChanged();

        if (value is null)
            return;

        RotationUniqueCount = value.Unique;
        RotationDuplicateCount = value.Duplicates;
        RotationErrorCount = value.ConnectionErrors;
        if (!string.IsNullOrWhiteSpace(value.Error))
            StatusMessage = value.Error;
    }

    private async Task RefreshStatusAsync()
    {
        try
        {
            LatestStatus = await _backend.GetProxyPoolCheckStatusAsync();
        }
        catch (HttpRequestException)
        {
            // backend momentarily unreachable -- keep the last known status
        }
        catch (TaskCanceledException)
        {
            // request timed out/was aborted -- keep the last known status
        }
    }

    [RelayCommand(CanExecute = nameof(CanStart))]
    private async Task StartAsync()
    {
        StatusMessage = "";
        RotationUniqueCount = 0;
        RotationDuplicateCount = 0;
        RotationErrorCount = 0;

        var protocol = RotationProtocolIndex == 1 ? "socks5" : "http";
        var mode = IsStickyMode ? "sticky" : "rotating";
        var requestCount = ParsePositiveInt(RotationRequestCount);
        var proxies = IsStickyMode
            ? ParseProxyList(RotationProxyText, protocol)
            : ParseSingleProxy(RotationProxyText, protocol);

        if (proxies.Count == 0)
        {
            StatusMessage = LocalizationService.Instance["Proxy.EmptyListError"];
            return;
        }

        if (IsRotatingMode && requestCount is null)
        {
            StatusMessage = LocalizationService.Instance["Rotation.RequestCountError"];
            return;
        }

        try
        {
            await _backend.StartProxyPoolCheckAsync(new ProxyPoolCheckStartRequest
            {
                Mode = mode,
                Protocol = protocol,
                Proxies = proxies,
                RequestCount = IsRotatingMode ? requestCount : null,
                Concurrency = 10,
            });
            await RefreshStatusAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }

    private bool CanStart()
    {
        if (IsRunning || string.IsNullOrWhiteSpace(RotationProxyText))
            return false;

        return IsStickyMode || ParsePositiveInt(RotationRequestCount) is not null;
    }

    private static int? ParsePositiveInt(string value) =>
        int.TryParse(value.Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out var parsed) && parsed > 0
            ? parsed
            : null;

    private static List<ProxyCheckItem> ParseSingleProxy(string text, string protocol)
    {
        var proxy = ParseProxyLine(text.Trim(), protocol);
        return proxy is null ? [] : [proxy];
    }

    private static List<ProxyCheckItem> ParseProxyList(string text, string protocol)
    {
        var items = new List<ProxyCheckItem>();
        foreach (var rawLine in text.Split('\n'))
        {
            var item = ParseProxyLine(rawLine.Trim(), protocol);
            if (item is not null)
                items.Add(item);
        }
        return items;
    }

    private static ProxyCheckItem? ParseProxyLine(string line, string protocol)
    {
        if (line.Length == 0)
            return null;

        var parts = line.Split(':');
        if (parts.Length < 2 || !int.TryParse(parts[1].Trim(), out var port))
            return null;

        var usernameIndex = parts.Length >= 5 && IsProtocol(parts[2]) ? 3 : 2;
        return new ProxyCheckItem
        {
            Host = parts[0].Trim(),
            Port = port,
            Type = protocol,
            Username = parts.Length > usernameIndex ? parts[usernameIndex].Trim() : null,
            Password = parts.Length > usernameIndex + 1 ? parts[usernameIndex + 1].Trim() : null,
        };
    }

    private static bool IsProtocol(string value)
    {
        var normalized = value.Trim().ToLowerInvariant().Replace(" ", "");
        return normalized is "http" or "socks5";
    }
}
