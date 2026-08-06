using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Windows;
using System.Windows.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using TgPoolLauncher.Localization;
using TgPoolLauncher.Models;
using TgPoolLauncher.Services;
using TgPoolLauncher.Shared;

namespace TgPoolLauncher.ViewModels;

public partial class DashboardViewModel : ObservableObject
{
    private readonly RecommendedToolsService _tools;
    private readonly BackendClient _backend;
    private readonly LicenseActivationClient _license;
    private readonly DispatcherTimer _proxyCoverageTimer;

    [ObservableProperty]
    private bool connected;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(HasUnproxiedAccounts))]
    private ProxyCoverageDto? proxyCoverage;

    public bool HasUnproxiedAccounts => ProxyCoverage is { UnproxiedCount: > 0 };

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(HasAccountDiscovery))]
    [NotifyPropertyChangedFor(nameof(AccountDiscoverySummaryText))]
    private AccountDiscoverySummary? accountDiscovery;

    public bool HasAccountDiscovery => AccountDiscovery is not null;

    public string AccountDiscoverySummaryText
    {
        get
        {
            if (AccountDiscovery is not { } summary)
                return "";
            var loc = LocalizationService.Instance;
            var text = string.Format(loc["Dashboard.AccountsDiscoveredFormat"], summary.LoadedCount);
            if (summary.FailedCount > 0)
                text += " " + string.Format(loc["Dashboard.AccountsDiscoveryFailedFormat"], summary.FailedCount);
            return text;
        }
    }

    public ObservableCollection<AccountStatusRow> AccountStatuses { get; } = new();

    public ObservableCollection<RecommendedToolRow> RecommendedTools { get; } = new();

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(LauncherUpdateButtonLabel))]
    [NotifyPropertyChangedFor(nameof(IsLauncherUpdateBusy))]
    [NotifyPropertyChangedFor(nameof(IsLauncherUpdateIdle))]
    [NotifyPropertyChangedFor(nameof(ShowLauncherUpdateBanner))]
    private ToolDownloadState launcherUpdateState = ToolDownloadState.Checking;

    [ObservableProperty]
    private string? launcherInstalledVersion;

    [ObservableProperty]
    private string? launcherLatestVersion;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(HasLauncherNotes))]
    private string launcherNotes = "";

    [ObservableProperty]
    private double launcherProgress;

    [ObservableProperty]
    private string launcherUpdateStatusText = "";

    public bool IsLauncherUpdateBusy =>
        LauncherUpdateState is ToolDownloadState.Checking or ToolDownloadState.Downloading;

    public bool IsLauncherUpdateIdle => !IsLauncherUpdateBusy;

    public bool HasLauncherNotes => !string.IsNullOrWhiteSpace(LauncherNotes);

    public string LauncherUpdateButtonLabel => LauncherUpdateState == ToolDownloadState.ReadyToInstall
        ? LocalizationService.Instance["Dashboard.LauncherInstallButton"]
        : LocalizationService.Instance["Dashboard.LauncherDownloadButton"];

    public bool ShowLauncherUpdateBanner => LauncherUpdateState is
        ToolDownloadState.UpdateAvailable or ToolDownloadState.Downloading
        or ToolDownloadState.ReadyToInstall or ToolDownloadState.CheckFailed;

    private string? _launcherLocalInstallerPath;

    public DashboardViewModel(
        EventStreamClient eventStream, RecommendedToolsService tools, BackendClient backend,
        LicenseActivationClient license)
    {
        _tools = tools;
        _backend = backend;
        _license = license;

        eventStream.EventReceived += OnEventReceived;
        eventStream.ConnectionStateChanged += isConnected =>
            Application.Current.Dispatcher.Invoke(() => Connected = isConnected);

        BuildRecommendedTools();
        LocalizationService.Instance.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(LocalizationService.CurrentLanguage))
                RefreshToolText();
        };

        // Check-on-startup is the "our system watches for updates itself" behavior --
        // one GitHub Releases lookup per tool, well within its unauthenticated rate limit.
        foreach (var row in RecommendedTools)
            _ = CheckForUpdateAsync(row);

        // Unlike the third-party tools above, this runs on every launch regardless of
        // license state -- it's the only update check an already-activated, returning
        // customer will ever see (TgPoolActivator's own check only fires when there is
        // no locally valid cached license, i.e. essentially never for them).
        _ = CheckForLauncherUpdateAsync();

        // Proxy coverage changes slowly (only when accounts/proxies are added or removed),
        // so this polls far less aggressively than job-status views.
        _proxyCoverageTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(15) };
        _proxyCoverageTimer.Tick += async (_, _) => await RefreshProxyCoverageAsync();
        _proxyCoverageTimer.Start();
        _ = RefreshProxyCoverageAsync();
    }

    private async Task RefreshProxyCoverageAsync()
    {
        try
        {
            ProxyCoverage = await _backend.GetProxyCoverageAsync();
        }
        catch (HttpRequestException)
        {
            // backend momentarily unreachable -- keep the last known coverage
        }
        catch (TaskCanceledException)
        {
        }
    }

    private void BuildRecommendedTools()
    {
        var loc = LocalizationService.Instance;
        RecommendedTools.Add(new RecommendedToolRow
        {
            Key = "npp",
            Name = "Notepad++",
            Description = loc["Dashboard.ToolNppDescription"],
            Icon = "FileDocumentEditOutline",
            GitHubRepo = "notepad-plus-plus/notepad-plus-plus",
            AssetMatches = name => name.Contains("Installer.x64", StringComparison.OrdinalIgnoreCase)
                && name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase),
        });
        RecommendedTools.Add(new RecommendedToolRow
        {
            Key = "dbbrowser",
            Name = "DB Browser for SQLite",
            Description = loc["Dashboard.ToolDbBrowserDescription"],
            Icon = "Database",
            GitHubRepo = "sqlitebrowser/sqlitebrowser",
            AssetMatches = name => name.Contains("win64", StringComparison.OrdinalIgnoreCase)
                && name.EndsWith(".msi", StringComparison.OrdinalIgnoreCase),
        });
        RecommendedTools.Add(new RecommendedToolRow
        {
            Key = "letos",
            Name = "Letos (SQLiteStudio)",
            Description = loc["Dashboard.ToolLetosDescription"],
            Icon = "DatabaseEdit",
            GitHubRepo = "pawelsalawa/letos",
            AssetMatches = name => name.Contains("windows-x64-setup", StringComparison.OrdinalIgnoreCase)
                && name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase),
        });
    }

    private void RefreshToolText()
    {
        var loc = LocalizationService.Instance;
        var descriptions = new Dictionary<string, string>
        {
            ["npp"] = loc["Dashboard.ToolNppDescription"],
            ["dbbrowser"] = loc["Dashboard.ToolDbBrowserDescription"],
            ["letos"] = loc["Dashboard.ToolLetosDescription"],
        };
        foreach (var row in RecommendedTools)
        {
            row.Description = descriptions[row.Key];
            row.StatusText = BuildStatusText(row);
        }
        OnPropertyChanged(nameof(LauncherUpdateButtonLabel));
    }

    [RelayCommand]
    private async Task DownloadOrRunAsync(RecommendedToolRow row)
    {
        if (row.IsBusy)
            return;

        if (row.State is ToolDownloadState.ReadyToInstall or ToolDownloadState.UpToDate
            && row.LocalInstallerPath is not null && File.Exists(row.LocalInstallerPath))
        {
            RunInstaller(row.LocalInstallerPath);
            return;
        }

        if (row.State == ToolDownloadState.CheckFailed && row.PendingAssetUrl is null)
        {
            await CheckForUpdateAsync(row);
            return;
        }

        await DownloadAsync(row);
    }

    private async Task CheckForUpdateAsync(RecommendedToolRow row)
    {
        row.State = ToolDownloadState.Checking;
        row.StatusText = LocalizationService.Instance["Dashboard.ToolChecking"];
        try
        {
            var latest = await _tools.GetLatestReleaseAsync(row.GitHubRepo, row.AssetMatches);
            if (latest is null)
            {
                row.State = ToolDownloadState.CheckFailed;
                row.StatusText = LocalizationService.Instance["Dashboard.ToolCheckFailed"];
                return;
            }

            var (version, assetUrl, assetName) = latest.Value;
            row.LatestVersion = version;
            row.PendingAssetUrl = assetUrl;
            row.PendingAssetName = assetName;
            row.InstalledVersion = _tools.GetInstalledVersion(row.Key);

            var localPath = Path.Combine(AppPaths.Tools, assetName);
            if (row.InstalledVersion == version && File.Exists(localPath))
            {
                row.LocalInstallerPath = localPath;
                row.State = ToolDownloadState.UpToDate;
            }
            else if (row.InstalledVersion is null)
            {
                row.State = ToolDownloadState.NotDownloaded;
            }
            else
            {
                row.State = ToolDownloadState.UpdateAvailable;
            }
            row.StatusText = BuildStatusText(row);
        }
        catch
        {
            row.State = ToolDownloadState.CheckFailed;
            row.StatusText = LocalizationService.Instance["Dashboard.ToolCheckFailed"];
        }
    }

    private async Task DownloadAsync(RecommendedToolRow row)
    {
        if (row.PendingAssetUrl is null || row.PendingAssetName is null || row.LatestVersion is null)
            return;

        row.State = ToolDownloadState.Downloading;
        row.Progress = 0;
        try
        {
            var progress = new Progress<double>(p => row.Progress = p);
            var path = await _tools.DownloadAsync(
                row.Key, row.PendingAssetUrl, row.PendingAssetName, row.LatestVersion, progress);
            row.LocalInstallerPath = path;
            row.InstalledVersion = row.LatestVersion;
            row.State = ToolDownloadState.ReadyToInstall;
            row.StatusText = LocalizationService.Instance["Dashboard.ToolReadyToInstall"];
        }
        catch
        {
            row.State = ToolDownloadState.CheckFailed;
            row.StatusText = LocalizationService.Instance["Dashboard.ToolDownloadFailed"];
        }
    }

    private async Task CheckForLauncherUpdateAsync()
    {
        LauncherUpdateState = ToolDownloadState.Checking;
        LauncherInstalledVersion = ResolveInstalledVersion();
        try
        {
            var release = await _license.TryGetLatestReleaseAsync();
            if (release is null)
            {
                LauncherUpdateState = ToolDownloadState.CheckFailed;
                LauncherUpdateStatusText = LocalizationService.Instance["Dashboard.LauncherUpdateCheckFailed"];
                return;
            }

            LauncherLatestVersion = release.LatestVersion;
            LauncherNotes = release.Notes;
            LauncherUpdateState =
                string.IsNullOrWhiteSpace(release.DownloadUrl)
                || LauncherInstalledVersion == release.LatestVersion
                    ? ToolDownloadState.UpToDate
                    : ToolDownloadState.UpdateAvailable;
            LauncherUpdateStatusText = LauncherUpdateState == ToolDownloadState.UpToDate
                ? string.Format(LocalizationService.Instance["Dashboard.LauncherUpToDateFormat"], LauncherInstalledVersion)
                : string.Format(
                    LocalizationService.Instance["Dashboard.LauncherUpdateAvailableFormat"],
                    LauncherInstalledVersion, release.LatestVersion);
        }
        catch
        {
            LauncherUpdateState = ToolDownloadState.CheckFailed;
            LauncherUpdateStatusText = LocalizationService.Instance["Dashboard.LauncherUpdateCheckFailed"];
        }
    }

    [RelayCommand]
    private async Task DownloadOrRunLauncherUpdateAsync()
    {
        if (IsLauncherUpdateBusy)
            return;

        if (LauncherUpdateState == ToolDownloadState.ReadyToInstall && _launcherLocalInstallerPath is not null)
        {
            RunLauncherUpdateInstaller(_launcherLocalInstallerPath);
            return;
        }

        if (LauncherUpdateState == ToolDownloadState.CheckFailed)
        {
            await CheckForLauncherUpdateAsync();
            return;
        }

        var release = await _license.TryGetLatestReleaseAsync();
        if (release is null || string.IsNullOrWhiteSpace(release.DownloadUrl))
            return;

        LauncherUpdateState = ToolDownloadState.Downloading;
        LauncherProgress = 0;
        try
        {
            var fileName = $"TelegramAndromedaSetup-{release.LatestVersion}.exe";
            var destPath = Path.Combine(AppPaths.Tools, fileName);
            var progress = new Progress<double>(p => LauncherProgress = p);
            await _license.DownloadInstallerAsync(release.DownloadUrl, destPath, progress);
            _launcherLocalInstallerPath = destPath;
            LauncherUpdateState = ToolDownloadState.ReadyToInstall;
            LauncherUpdateStatusText = LocalizationService.Instance["Dashboard.LauncherReadyToInstall"];
        }
        catch
        {
            LauncherUpdateState = ToolDownloadState.CheckFailed;
            LauncherUpdateStatusText = LocalizationService.Instance["Dashboard.LauncherDownloadFailed"];
        }
    }

    /// <summary>
    /// Unlike <see cref="RunInstaller"/> (third-party tools, which stay independent of
    /// this app's own process), our own installer needs to overwrite the exe that's
    /// currently running it -- so this closes the app right after launching the
    /// installer, giving Inno Setup's [Files] step an unlocked file to replace.
    /// </summary>
    private static void RunLauncherUpdateInstaller(string path)
    {
        try
        {
            Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
        }
        catch
        {
            return;
        }
        Application.Current.Shutdown();
    }

    private static string? ResolveInstalledVersion()
    {
        try
        {
            var exePath = Process.GetCurrentProcess().MainModule?.FileName;
            if (exePath is null)
                return null;
            var info = FileVersionInfo.GetVersionInfo(exePath);
            if (string.IsNullOrWhiteSpace(info.ProductVersion))
                return null;
            // SourceLink appends "+<git-sha>" to ProductVersion on Release builds --
            // strip it so comparing against the server's plain LATEST_LAUNCHER_VERSION
            // ("1.1.0") doesn't always read as "an update is available".
            var plusIndex = info.ProductVersion.IndexOf('+');
            return plusIndex < 0 ? info.ProductVersion : info.ProductVersion[..plusIndex];
        }
        catch
        {
            return null;
        }
    }

    private static string BuildStatusText(RecommendedToolRow row)
    {
        var loc = LocalizationService.Instance;
        return row.State switch
        {
            ToolDownloadState.UpToDate => string.Format(loc["Dashboard.ToolUpToDateFormat"], row.InstalledVersion),
            ToolDownloadState.NotDownloaded => string.Format(loc["Dashboard.ToolAvailableFormat"], row.LatestVersion),
            ToolDownloadState.UpdateAvailable => string.Format(
                loc["Dashboard.ToolUpdateAvailableFormat"], row.InstalledVersion, row.LatestVersion),
            ToolDownloadState.ReadyToInstall => loc["Dashboard.ToolReadyToInstall"],
            ToolDownloadState.CheckFailed => loc["Dashboard.ToolCheckFailed"],
            _ => loc["Dashboard.ToolChecking"],
        };
    }

    private static void RunInstaller(string path)
    {
        try
        {
            Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
        }
        catch
        {
            // best-effort -- a failed installer launch must not crash the dashboard
        }
    }

    [RelayCommand]
    private void DismissAccountDiscovery() => AccountDiscovery = null;

    // Fires from EventStreamClient's background receive loop -- must marshal
    // to the UI thread before touching ObservableCollection/bound properties.
    private void OnEventReceived(EventEnvelope envelope)
    {
        if (envelope.Type == "AccountsDiscoveredEvent")
        {
            OnAccountsDiscovered(envelope);
            return;
        }

        if (envelope.Type != "AccountStatusEvent")
            return;

        var phone = envelope.Data.GetProperty("phone").GetString() ?? "";
        var status = envelope.Data.GetProperty("status").GetString() ?? "";
        var detail = envelope.Data.TryGetProperty("detail", out var d) ? d.GetString() ?? "" : "";

        Application.Current.Dispatcher.Invoke(() =>
        {
            var row = AccountStatuses.FirstOrDefault(r => r.Phone == phone);
            if (row is null)
            {
                AccountStatuses.Add(new AccountStatusRow { Phone = phone, Status = status, Detail = detail });
            }
            else
            {
                row.Status = status;
                row.Detail = detail;
            }
        });
    }

    private void OnAccountsDiscovered(EventEnvelope envelope)
    {
        var loadedCount = envelope.Data.GetProperty("loaded_count").GetInt32();
        var failedCount = envelope.Data.GetProperty("failed_count").GetInt32();
        var loadedPhones = envelope.Data.GetProperty("loaded_phones")
            .EnumerateArray().Select(e => e.GetString() ?? "").ToList();
        var failedReasons = envelope.Data.GetProperty("failed_reasons")
            .EnumerateArray().Select(e => e.GetString() ?? "").ToList();

        Application.Current.Dispatcher.Invoke(() =>
        {
            AccountDiscovery = new AccountDiscoverySummary(loadedCount, loadedPhones, failedCount, failedReasons);
        });
    }
}
