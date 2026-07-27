using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
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

    // --- Source picker (browse joined chats/channels instead of typing them) ---
    [ObservableProperty]
    private bool isSourcePickerOpen;

    [ObservableProperty]
    private string sourceSearchText = "";

    [ObservableProperty]
    private string sourcePickerStatus = "";

    private List<SelectableSourceRow> _allSourceRows = new();

    public ObservableCollection<SelectableSourceRow> FilteredSources { get; } = new();

    private string? _lastOpenedReportPath;

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
        DownloadTxtCommand.NotifyCanExecuteChanged();

        Sources.Clear();
        if (value is not null)
            foreach (var source in value.Sources)
                Sources.Add(source);

        // A console opens with this run's numbers the moment it finishes --
        // guarded by report path so a still-finished status from later polls
        // doesn't reopen it, but a genuinely new run (new report path) does.
        if (value?.Finished == true && !string.IsNullOrWhiteSpace(value.ReportPath)
            && value.ReportPath != _lastOpenedReportPath)
        {
            _lastOpenedReportPath = value.ReportPath;
            OpenReportConsole(value.ReportPath);
        }
    }

    private static void OpenReportConsole(string reportPath)
    {
        try
        {
            var fullPath = Path.IsPathRooted(reportPath) ? reportPath : Path.Combine(AppPaths.Root, reportPath);
            // The report file is UTF-16 (with BOM) specifically so `type` renders Cyrillic
            // correctly here without any chcp/codepage juggling -- cmd.exe's `type` reads
            // UTF-16-with-BOM via its native wide-char path, sidestepping the legacy OEM
            // byte-translation that garbles multi-byte UTF-8 even under `chcp 65001`.
            Process.Start(new ProcessStartInfo
            {
                FileName = "cmd.exe",
                Arguments = $"/k type \"{fullPath}\"",
                UseShellExecute = true,
            });
        }
        catch
        {
            // best-effort -- a failed console popup must not disrupt the rest of the UI
        }
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
                Language = LocalizationService.Instance.CurrentLanguage.ToString().ToLowerInvariant(),
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

    private bool CanDownloadTxt() => !string.IsNullOrWhiteSpace(LatestStatus?.TxtPath);

    [RelayCommand(CanExecute = nameof(CanDownloadTxt))]
    private void DownloadTxt()
    {
        var source = LatestStatus?.TxtPath;
        if (string.IsNullOrWhiteSpace(source) || !File.Exists(source))
            return;

        var dialog = new Microsoft.Win32.SaveFileDialog
        {
            Title = LocalizationService.Instance["Parsing.DownloadTxtDialogTitle"],
            FileName = Path.GetFileName(source),
            Filter = "Text files (*.txt)|*.txt|All files|*.*",
            InitialDirectory = AppPaths.Exports,
        };
        if (dialog.ShowDialog() == true)
            File.Copy(source, dialog.FileName, overwrite: true);
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

    [RelayCommand]
    private async Task OpenSourcePickerAsync()
    {
        IsSourcePickerOpen = true;
        SourceSearchText = "";
        SourcePickerStatus = LocalizationService.Instance["Parsing.SourcesLoading"];
        _allSourceRows.Clear();
        FilteredSources.Clear();

        try
        {
            var sources = await _backend.GetParsingSourcesAsync();
            _allSourceRows = sources.Select(s => new SelectableSourceRow(s)).ToList();
            ApplySourceFilter();
            SourcePickerStatus = string.Format(
                LocalizationService.Instance["Parsing.SourcesLoadedFormat"], _allSourceRows.Count);
        }
        catch (Exception ex)
        {
            SourcePickerStatus = string.Format(
                LocalizationService.Instance["Parsing.SourcesLoadErrorFormat"], ex.Message);
        }
    }

    partial void OnSourceSearchTextChanged(string value) => ApplySourceFilter();

    private void ApplySourceFilter()
    {
        FilteredSources.Clear();
        var query = SourceSearchText?.Trim() ?? "";
        var matches = query.Length == 0
            ? _allSourceRows
            : _allSourceRows.Where(row =>
                row.Source.Title.Contains(query, StringComparison.OrdinalIgnoreCase)
                || row.Source.Identifier.Contains(query, StringComparison.OrdinalIgnoreCase));
        foreach (var row in matches)
            FilteredSources.Add(row);
    }

    [RelayCommand]
    private void CloseSourcePicker() => IsSourcePickerOpen = false;

    [RelayCommand]
    private void UseSelectedSources()
    {
        var selected = _allSourceRows.Where(row => row.IsSelected).Select(row => row.Source.Identifier).ToList();
        if (selected.Count > 0)
        {
            var existing = EntitiesText
                .Split(new[] { '\n', ',' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .ToList();
            var combined = existing.Concat(selected).Distinct();
            EntitiesText = string.Join("\n", combined);
        }
        IsSourcePickerOpen = false;
    }
}
