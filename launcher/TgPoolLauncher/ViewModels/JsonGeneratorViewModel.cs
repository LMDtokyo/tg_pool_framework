using System.Collections.ObjectModel;
using System.IO;
using System.Net.Http;
using System.Windows.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
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
    private string statusMessage = "Ready to generate Telegram Expert JSON sidecars.";

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
            StatusMessage = $"Generating files… {value.Results.Count} of {value.Total}";
        else if (value?.Finished == true)
            StatusMessage = value.Cancelled
                ? $"Stopped after {value.Results.Count} of {value.Total} accounts."
                : $"Completed {value.Results.Count} of {value.Total} accounts.";
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
            StatusMessage = "Starting JSON generation…";
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
            StatusMessage = "Activity cleared.";
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
        StatusMessage = "Settings reset to project defaults.";
    }

    [RelayCommand]
    private void BrowseDatabase()
    {
        var dialog = new Microsoft.Win32.OpenFileDialog
        {
            Title = "Select the parameter generator database",
            Filter = "Parameter databases (*.xlsx;*.xlsm;*.csv;*.json)|*.xlsx;*.xlsm;*.csv;*.json|All files (*.*)|*.*",
            InitialDirectory = Path.GetDirectoryName(DatabasePath),
        };
        if (dialog.ShowDialog() == true)
            DatabasePath = dialog.FileName;
    }

    [RelayCommand]
    private void BrowseSessionsDir() => BrowseFolder("Select the folder with .session files", SessionsDir, value => SessionsDir = value);

    [RelayCommand]
    private void BrowseOutputDir() => BrowseFolder("Select the folder for generated files", OutputDir, value => OutputDir = value);

    private static void BrowseFolder(string title, string initialDirectory, Action<string> assign)
    {
        var dialog = new Microsoft.Win32.OpenFolderDialog { Title = title, InitialDirectory = initialDirectory };
        if (dialog.ShowDialog() == true)
            assign(dialog.FolderName);
    }
}
