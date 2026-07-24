using System.Collections.ObjectModel;
using System.Net.Http;
using System.Windows.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using TgPoolLauncher.Localization;
using TgPoolLauncher.Models;
using TgPoolLauncher.Services;

namespace TgPoolLauncher.ViewModels;

/// <summary>
/// Owns tdata-conversion start and the /tdata_convert/status polling loop.
/// Same skeleton as ProxyCheckViewModel; no Stop command since
/// convert_batch_tdata() has no cancellation hook.
/// </summary>
public partial class TdataConvertViewModel : ObservableObject
{
    private readonly BackendClient _backend;
    private readonly DispatcherTimer _statusTimer;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string tdataDir = AppPaths.Tdata;

    [ObservableProperty]
    private string outputDir = AppPaths.Sessions;

    [ObservableProperty]
    private bool allAccounts;

    [ObservableProperty]
    private TdataConvertStatusDto? latestStatus;

    [ObservableProperty]
    private string statusMessage = "";

    public bool IsRunning => LatestStatus?.Running == true;

    public ObservableCollection<TdataConvertResult> Results { get; } = new();

    public TdataConvertViewModel(BackendClient backend)
    {
        _backend = backend;
        _statusTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1.5) };
        _statusTimer.Tick += async (_, _) => await RefreshStatusAsync();
        _statusTimer.Start();
    }

    partial void OnLatestStatusChanged(TdataConvertStatusDto? value)
    {
        OnPropertyChanged(nameof(IsRunning));
        StartCommand.NotifyCanExecuteChanged();

        Results.Clear();
        if (value is not null)
            foreach (var result in value.Results)
                Results.Add(result);
    }

    private async Task RefreshStatusAsync()
    {
        try
        {
            LatestStatus = await _backend.GetTdataConvertStatusAsync();
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

    [RelayCommand(CanExecute = nameof(CanStart))]
    private async Task StartAsync()
    {
        StatusMessage = "";
        try
        {
            await _backend.StartTdataConvertAsync(new TdataConvertStartRequest
            {
                TdataDir = TdataDir,
                OutputDir = string.IsNullOrWhiteSpace(OutputDir) ? "sessions" : OutputDir,
                AllAccounts = AllAccounts,
            });
            await RefreshStatusAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }

    private bool CanStart() => !IsRunning && !string.IsNullOrWhiteSpace(TdataDir);

    [RelayCommand]
    private void BrowseTdataDir()
    {
        var dialog = new Microsoft.Win32.OpenFolderDialog
        {
            Title = LocalizationService.Instance["Tdata.BrowseTdataDialogTitle"],
            InitialDirectory = string.IsNullOrWhiteSpace(TdataDir) ? AppPaths.Tdata : TdataDir,
        };
        if (dialog.ShowDialog() == true)
            TdataDir = dialog.FolderName;
    }

    [RelayCommand]
    private void BrowseOutputDir()
    {
        var dialog = new Microsoft.Win32.OpenFolderDialog
        {
            Title = LocalizationService.Instance["Tdata.BrowseOutputDialogTitle"],
            InitialDirectory = string.IsNullOrWhiteSpace(OutputDir) ? AppPaths.Sessions : OutputDir,
        };
        if (dialog.ShowDialog() == true)
            OutputDir = dialog.FolderName;
    }
}
