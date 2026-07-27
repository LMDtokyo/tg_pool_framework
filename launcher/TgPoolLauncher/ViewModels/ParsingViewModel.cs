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
/// Owns parsing job start/stop and the /parsing/status polling loop. Same
/// skeleton as the other job view-models (DispatcherTimer + Start/Stop RelayCommands),
/// since parsing jobs -- unlike proxy check / tdata convert -- support
/// graceful cancellation via the shared PoolAccessGuard/shutdown_event.
/// </summary>
public partial class ParsingViewModel : ObservableObject
{
    private readonly BackendClient _backend;
    private readonly DispatcherTimer _statusTimer;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string entitiesText = "";

    [ObservableProperty]
    private string strategy = "members";

    [ObservableProperty]
    private int? topicId;

    [ObservableProperty]
    private int? lastSeenDays;

    [ObservableProperty]
    private string gender = "";

    [ObservableProperty]
    private bool hasAvatar;

    [ObservableProperty]
    private bool premium;

    [ObservableProperty]
    private bool excludeBots = true;

    [ObservableProperty]
    private string exportMode = "full";

    [ObservableProperty]
    private string exportPath = AppPaths.Exports;

    [ObservableProperty]
    private ParseStatusDto? latestStatus;

    [ObservableProperty]
    private string statusMessage = "";

    public bool IsRunning => LatestStatus?.Running == true;

    public ObservableCollection<string> Sources { get; } = new();

    public ParsingViewModel(BackendClient backend)
    {
        _backend = backend;
        _statusTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1.5) };
        _statusTimer.Tick += async (_, _) => await RefreshStatusAsync();
        _statusTimer.Start();
    }

    partial void OnLatestStatusChanged(ParseStatusDto? value)
    {
        OnPropertyChanged(nameof(IsRunning));
        StartCommand.NotifyCanExecuteChanged();
        StopCommand.NotifyCanExecuteChanged();

        Sources.Clear();
        if (value is not null)
            foreach (var source in value.Sources)
                Sources.Add(source);
    }

    private async Task RefreshStatusAsync()
    {
        try
        {
            LatestStatus = await _backend.GetParsingStatusAsync();
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
        var entities = EntitiesText
            .Split(new[] { '\n', ',' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .ToList();

        if (entities.Count == 0)
        {
            StatusMessage = LocalizationService.Instance["Parsing.NoSourcesError"];
            return;
        }

        try
        {
            await _backend.StartParsingAsync(new ParseStartRequest
            {
                Entities = entities,
                Strategy = Strategy,
                TopicId = TopicId,
                Filters = new ParseFilterIn
                {
                    LastSeenDays = LastSeenDays,
                    Gender = string.IsNullOrWhiteSpace(Gender) ? null : Gender,
                    HasAvatar = HasAvatar,
                    Premium = Premium,
                    ExcludeBots = ExcludeBots,
                },
                ExportMode = ExportMode,
                ExportPath = string.IsNullOrWhiteSpace(ExportPath) ? null : ExportPath,
            });
            await RefreshStatusAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }

    private bool CanStart() => !IsRunning && !string.IsNullOrWhiteSpace(EntitiesText);

    [RelayCommand]
    private void BrowseExportPath()
    {
        var dialog = new Microsoft.Win32.OpenFolderDialog
        {
            Title = LocalizationService.Instance["Parsing.BrowseExportDialogTitle"],
            InitialDirectory = string.IsNullOrWhiteSpace(ExportPath) ? AppPaths.Exports : ExportPath,
        };
        if (dialog.ShowDialog() == true)
            ExportPath = dialog.FolderName;
    }

    [RelayCommand(CanExecute = nameof(IsRunning))]
    private async Task StopAsync()
    {
        try
        {
            await _backend.StopParsingAsync();
            await RefreshStatusAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }
}
