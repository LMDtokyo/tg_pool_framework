using System.Collections.ObjectModel;
using System.IO;
using System.Net.Http;
using System.Windows.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using TgPoolLauncher.Localization;
using TgPoolLauncher.Models;
using TgPoolLauncher.Services;

namespace TgPoolLauncher.ViewModels;

public partial class JsonGeneratorViewModel : ObservableObject
{
    private readonly BackendClient _backend;
    private readonly DispatcherTimer _statusTimer;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string databasePath = Path.Combine(AppPaths.Fingerprints, "telegram_devices.xlsx");

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string sessionsDir = AppPaths.Sessions;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string outputDir = AppPaths.JsonGenerator;

    [ObservableProperty]
    private JsonGeneratorStatusDto? latestStatus;

    [ObservableProperty]
    private string statusMessage = LocalizationService.Instance["JsonGenerator.ReadyStatus"];

    public bool IsRunning => LatestStatus?.Running == true;
    public ObservableCollection<JsonGeneratorResult> Results { get; } = new();

    public JsonGeneratorViewModel(BackendClient backend)
    {
        _backend = backend;
        _statusTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        _statusTimer.Tick += async (_, _) => await RefreshStatusAsync();
        _statusTimer.Start();
    }

    partial void OnLatestStatusChanged(JsonGeneratorStatusDto? value)
    {
        OnPropertyChanged(nameof(IsRunning));
        StartCommand.NotifyCanExecuteChanged();
        StopCommand.NotifyCanExecuteChanged();
        ClearCommand.NotifyCanExecuteChanged();

        Results.Clear();
        if (value is not null)
            foreach (var result in value.Results)
                Results.Add(result);

        if (!string.IsNullOrWhiteSpace(value?.Error))
            StatusMessage = value.Error;
        else if (value?.Running == true)
            StatusMessage = string.Format(
                LocalizationService.Instance["JsonGenerator.GeneratingStatusFormat"],
                value.Results.Count, value.Total);
        else if (value?.Finished == true)
            StatusMessage = string.Format(
                value.Cancelled
                    ? LocalizationService.Instance["JsonGenerator.StoppedStatusFormat"]
                    : LocalizationService.Instance["JsonGenerator.CompletedStatusFormat"],
                value.Results.Count, value.Total);
    }

    private async Task RefreshStatusAsync()
    {
        try
        {
            LatestStatus = await _backend.GetJsonGeneratorStatusAsync();
        }
        catch (HttpRequestException) { }
        catch (TaskCanceledException) { }
    }

    [RelayCommand(CanExecute = nameof(CanStart))]
    private async Task StartAsync()
    {
        try
        {
            StatusMessage = LocalizationService.Instance["JsonGenerator.StartingStatus"];
            await _backend.StartJsonGeneratorAsync(new JsonGeneratorStartRequest
            {
                DatabasePath = DatabasePath,
                SessionsDir = SessionsDir,
                OutputDir = OutputDir,
            });
            await RefreshStatusAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }

    private bool CanStart() => !IsRunning
        && !string.IsNullOrWhiteSpace(DatabasePath)
        && !string.IsNullOrWhiteSpace(SessionsDir)
        && !string.IsNullOrWhiteSpace(OutputDir);

    [RelayCommand(CanExecute = nameof(CanStop))]
    private async Task StopAsync()
    {
        try
        {
            await _backend.StopJsonGeneratorAsync();
            await RefreshStatusAsync();
        }
        catch (Exception ex) { StatusMessage = ex.Message; }
    }

    private bool CanStop() => IsRunning;

    [RelayCommand(CanExecute = nameof(CanClear))]
    private async Task ClearAsync()
    {
        try
        {
            await _backend.ClearJsonGeneratorAsync();
            Results.Clear();
            StatusMessage = LocalizationService.Instance["JsonGenerator.ActivityClearedStatus"];
            await RefreshStatusAsync();
        }
        catch (Exception ex) { StatusMessage = ex.Message; }
    }

    private bool CanClear() => !IsRunning;

    [RelayCommand]
    private void Reset()
    {
        DatabasePath = Path.Combine(AppPaths.Fingerprints, "telegram_devices.xlsx");
        SessionsDir = AppPaths.Sessions;
        OutputDir = AppPaths.JsonGenerator;
        StatusMessage = LocalizationService.Instance["JsonGenerator.SettingsResetStatus"];
    }

    [RelayCommand]
    private void BrowseDatabase()
    {
        var dialog = new Microsoft.Win32.OpenFileDialog
        {
            Title = LocalizationService.Instance["JsonGenerator.BrowseDatabaseDialogTitle"],
            Filter = LocalizationService.Instance["JsonGenerator.BrowseDatabaseDialogFilter"],
            InitialDirectory = Path.GetDirectoryName(DatabasePath),
        };
        if (dialog.ShowDialog() == true)
            DatabasePath = dialog.FileName;
    }

    [RelayCommand]
    private void BrowseSessionsDir() => BrowseFolder(
        LocalizationService.Instance["JsonGenerator.BrowseSessionsDirDialogTitle"], SessionsDir, value => SessionsDir = value);

    [RelayCommand]
    private void BrowseOutputDir() => BrowseFolder(
        LocalizationService.Instance["JsonGenerator.BrowseOutputDirDialogTitle"], OutputDir, value => OutputDir = value);

    private static void BrowseFolder(string title, string initialDirectory, Action<string> assign)
    {
        var dialog = new Microsoft.Win32.OpenFolderDialog { Title = title, InitialDirectory = initialDirectory };
        if (dialog.ShowDialog() == true)
            assign(dialog.FolderName);
    }
}
