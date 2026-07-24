using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Net.Http;
using System.Windows;
using System.Windows.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.Win32;
using TgPoolLauncher.Localization;
using TgPoolLauncher.Models;
using TgPoolLauncher.Services;

namespace TgPoolLauncher.ViewModels;

/// <summary>
/// Owns campaign start/stop and the single /campaign/status polling loop.
/// DashboardViewModel is injected with the same DI-singleton instance and
/// reads LatestStatus reactively -- avoids a second competing poll timer.
/// </summary>
public partial class CampaignViewModel : ObservableObject
{
    private readonly BackendClient _backend;
    private readonly DispatcherTimer _statusTimer;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string target = "";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string messageText = "";

    [ObservableProperty]
    private string mediaPath = "";

    [ObservableProperty]
    private string buttonsRaw = "";

    [ObservableProperty]
    private string parseMode = "markdown";

    [ObservableProperty]
    private CampaignStatusDto? latestStatus;

    [ObservableProperty]
    private string statusMessage = "";

    [ObservableProperty]
    private int eligibleAccountsCount;

    [ObservableProperty]
    private int activeProxiesCount;

    [ObservableProperty]
    private bool isAccountPickerOpen;

    [ObservableProperty]
    private int selectedAccountsCount;

    private int _tickCount;

    public bool IsRunning => LatestStatus?.Running == true;

    public ObservableCollection<CampaignLogRow> Log { get; } = new();

    public ObservableCollection<SelectableAccountRow> PickerAccounts { get; } = new();

    public CampaignViewModel(BackendClient backend, EventStreamClient eventStream)
    {
        _backend = backend;

        // DispatcherTimer.Tick fires on the UI thread, so the async status
        // update below resumes on the UI thread after each await -- no
        // manual Dispatcher.Invoke needed here (unlike EventStreamClient's
        // background receive loop).
        _statusTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1.5) };
        _statusTimer.Tick += async (_, _) =>
        {
            await RefreshStatusAsync();
            // Pool composition changes far less often than campaign progress --
            // every 5th tick (~7.5s) is plenty fresh without hammering /accounts.
            if (_tickCount++ % 5 == 0)
                await RefreshPoolSummaryAsync();
        };
        _statusTimer.Start();

        eventStream.EventReceived += OnEventReceived;
    }

    private async Task RefreshPoolSummaryAsync()
    {
        try
        {
            var accounts = await _backend.GetAccountsAsync(status: "alive");
            EligibleAccountsCount = accounts.Count;
            ActiveProxiesCount = accounts.Count(a => a.Proxy?.IsActive == true);
        }
        catch (HttpRequestException)
        {
            // backend momentarily unreachable -- keep the last known counts
        }
        catch (TaskCanceledException)
        {
            // request timed out/was aborted (e.g. backend restarting) -- same as above
        }
    }

    partial void OnLatestStatusChanged(CampaignStatusDto? value)
    {
        OnPropertyChanged(nameof(IsRunning));
        StartCommand.NotifyCanExecuteChanged();
        StopCommand.NotifyCanExecuteChanged();
    }

    private async Task RefreshStatusAsync()
    {
        try
        {
            LatestStatus = await _backend.GetCampaignStatusAsync();
        }
        catch (HttpRequestException)
        {
            // backend momentarily unreachable -- keep the last known status
        }
        catch (TaskCanceledException)
        {
            // request timed out/was aborted (e.g. backend restarting) -- same as above
        }
    }

    // Fires from EventStreamClient's background receive loop -- must marshal
    // to the UI thread before touching the ObservableCollection.
    private void OnEventReceived(EventEnvelope envelope)
    {
        if (envelope.Type != "MessageDeliveredEvent")
            return;

        var workerPhone = envelope.Data.GetProperty("worker_phone").GetString() ?? "";
        var recipient = envelope.Data.GetProperty("recipient").GetString() ?? "";
        var success = envelope.Data.TryGetProperty("success", out var s) && s.GetBoolean();
        var error = envelope.Data.TryGetProperty("error", out var e) ? e.GetString() ?? "" : "";

        var message = success ? $"→ {recipient}" : $"→ {recipient} ({(string.IsNullOrEmpty(error) ? LocalizationService.Instance["Campaign.GenericError"] : error)})";

        Application.Current.Dispatcher.Invoke(() =>
        {
            Log.Insert(0, new CampaignLogRow(DateTime.Now.ToString("HH:mm:ss"), workerPhone, message, success));
            // Bounded -- this is a live tail, not an archive (RecheckAsync/exports cover history).
            while (Log.Count > 200)
                Log.RemoveAt(Log.Count - 1);
        });
    }

    [RelayCommand(CanExecute = nameof(CanStart))]
    private async Task StartAsync()
    {
        StatusMessage = "";
        try
        {
            await _backend.StartCampaignAsync(new CampaignStartRequest
            {
                Target = Target,
                Message = MessageText,
                MediaPath = string.IsNullOrWhiteSpace(MediaPath) ? null : MediaPath,
                ButtonsRaw = string.IsNullOrWhiteSpace(ButtonsRaw) ? null : ButtonsRaw,
                ParseMode = string.IsNullOrWhiteSpace(ParseMode) ? null : ParseMode,
            });
            await RefreshStatusAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }

    private bool CanStart() =>
        !IsRunning && !string.IsNullOrWhiteSpace(Target) && !string.IsNullOrWhiteSpace(MessageText);

    [RelayCommand(CanExecute = nameof(IsRunning))]
    private async Task StopAsync()
    {
        try
        {
            await _backend.StopCampaignAsync();
            await RefreshStatusAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }

    [RelayCommand]
    private void ClearLog() => Log.Clear();

    [RelayCommand]
    private void ResetForm()
    {
        Target = "";
        MessageText = "";
        MediaPath = "";
        ButtonsRaw = "";
        ParseMode = "markdown";
    }

    [RelayCommand]
    private void BrowseMediaFile()
    {
        var dialog = new OpenFileDialog
        {
            Title = LocalizationService.Instance["Campaign.MediaDialogTitle"],
            Filter = LocalizationService.Instance["Campaign.MediaDialogFilter"],
        };
        if (dialog.ShowDialog() == true)
            MediaPath = dialog.FileName;
    }

    [RelayCommand]
    private void OpenResultsFolder()
    {
        try
        {
            Process.Start(new ProcessStartInfo { FileName = AppPaths.Logs, UseShellExecute = true });
        }
        catch (Exception ex)
        {
            StatusMessage = string.Format(LocalizationService.Instance["Campaign.OpenFolderErrorFormat"], ex.Message);
        }
    }

    [RelayCommand]
    private async Task OpenAccountPickerAsync()
    {
        IsAccountPickerOpen = true;
        if (PickerAccounts.Count > 0)
            return;

        try
        {
            var accounts = await _backend.GetAccountsAsync();
            foreach (var account in accounts)
            {
                var row = new SelectableAccountRow(account);
                row.PropertyChanged += (_, e) =>
                {
                    if (e.PropertyName == nameof(SelectableAccountRow.IsSelected))
                        SelectedAccountsCount = PickerAccounts.Count(r => r.IsSelected);
                };
                PickerAccounts.Add(row);
            }
        }
        catch (Exception ex)
        {
            StatusMessage = string.Format(LocalizationService.Instance["Campaign.LoadAccountsErrorFormat"], ex.Message);
        }
    }

    [RelayCommand]
    private void CloseAccountPicker() => IsAccountPickerOpen = false;
}
