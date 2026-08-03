using System.Collections.ObjectModel;
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
/// Owns session-to-tdata conversion start and the /session_convert/status
/// polling loop. Same skeleton as TdataConvertViewModel; no Stop command
/// since convert_batch_sessions() has no cancellation hook.
/// </summary>
public partial class SessionConvertViewModel : ObservableObject
{
    private readonly BackendClient _backend;
    private readonly DispatcherTimer _statusTimer;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string itemsText = "";

    [ObservableProperty]
    private string outputBaseDir = AppPaths.TdataExports;

    [ObservableProperty]
    private SessionConvertStatusDto? latestStatus;

    [ObservableProperty]
    private string statusMessage = "";

    public bool IsRunning => LatestStatus?.Running == true;

    public ObservableCollection<SessionConvertResult> Results { get; } = new();

    public SessionConvertViewModel(BackendClient backend)
    {
        _backend = backend;
        _statusTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1.5) };
        _statusTimer.Tick += async (_, _) => await RefreshStatusAsync();
        _statusTimer.Start();
    }

    partial void OnLatestStatusChanged(SessionConvertStatusDto? value)
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
            LatestStatus = await _backend.GetSessionConvertStatusAsync();
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
        var items = ParseItems(ItemsText);
        if (items.Count == 0)
        {
            StatusMessage = LocalizationService.Instance["SessionConvert.EmptyListError"];
            return;
        }

        try
        {
            await _backend.StartSessionConvertAsync(new SessionConvertStartRequest
            {
                Items = items,
                OutputBaseDir = string.IsNullOrWhiteSpace(OutputBaseDir) ? "tdata_exports" : OutputBaseDir,
            });
            await RefreshStatusAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }

    private bool CanStart() => !IsRunning && !string.IsNullOrWhiteSpace(ItemsText);

    [RelayCommand]
    private void BrowseOutputBaseDir()
    {
        var dialog = new Microsoft.Win32.OpenFolderDialog
        {
            Title = LocalizationService.Instance["SessionConvert.BrowseOutputDialogTitle"],
            InitialDirectory = string.IsNullOrWhiteSpace(OutputBaseDir) ? AppPaths.TdataExports : OutputBaseDir,
        };
        if (dialog.ShowDialog() == true)
            OutputBaseDir = dialog.FolderName;
    }

    /// <summary>Scans a chosen folder for .session+.json pairs and appends them to ItemsText.</summary>
    [RelayCommand]
    private void AddFromFolder()
    {
        var dialog = new Microsoft.Win32.OpenFolderDialog
        {
            Title = LocalizationService.Instance["SessionConvert.AddFromFolderDialogTitle"],
            InitialDirectory = AppPaths.Accounts,
        };
        if (dialog.ShowDialog() != true)
            return;

        var found = Directory.GetFiles(dialog.FolderName, "*.session")
            .Select(sessionPath => (SessionPath: sessionPath, JsonPath: Path.ChangeExtension(sessionPath, ".json")))
            .Where(pair => File.Exists(pair.JsonPath))
            .Select(pair => $"{pair.SessionPath}|{pair.JsonPath}|{Path.GetFileNameWithoutExtension(pair.SessionPath)}")
            .ToList();

        if (found.Count == 0)
        {
            StatusMessage = LocalizationService.Instance["SessionConvert.NoPairsFoundError"];
            return;
        }

        var existing = ItemsText.TrimEnd();
        ItemsText = (existing.Length > 0 ? existing + "\n" : "") + string.Join("\n", found);
        StatusMessage = "";
    }

    /// <summary>Format: one entry per line, "session_path|json_path|output_subdir".</summary>
    private static List<SessionConvertItem> ParseItems(string text)
    {
        var items = new List<SessionConvertItem>();
        foreach (var rawLine in text.Split('\n'))
        {
            var line = rawLine.Trim();
            if (line.Length == 0)
                continue;

            var parts = line.Split('|');
            if (parts.Length < 3)
                continue;

            var sessionPath = parts[0].Trim();
            var jsonPath = parts[1].Trim();
            var outputSubdir = parts[2].Trim();
            if (sessionPath.Length == 0 || jsonPath.Length == 0 || outputSubdir.Length == 0)
                continue;

            items.Add(new SessionConvertItem
            {
                SessionPath = sessionPath,
                JsonPath = jsonPath,
                OutputSubdir = outputSubdir,
            });
        }
        return items;
    }
}
