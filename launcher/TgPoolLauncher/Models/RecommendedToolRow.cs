using CommunityToolkit.Mvvm.ComponentModel;

namespace TgPoolLauncher.Models;

public enum ToolDownloadState
{
    Checking,
    NotDownloaded,
    UpToDate,
    UpdateAvailable,
    Downloading,
    ReadyToInstall,
    CheckFailed,
}

/// <summary>
/// One entry in the dashboard's "Necessary Programs" list -- a third-party
/// tool that pairs well with this app's own file exports (SQLite databases,
/// plain-text audience lists). Installers are fetched straight from the
/// tool's own official GitHub Releases on click/at startup (never mirrored
/// on our own infrastructure -- GitHub's CDN is more reliable than anything
/// we'd run, and re-hosting someone else's binary is a maintenance and
/// trust liability with no upside), so the download happens inside this
/// app instead of bouncing the user out to a browser, and version staleness
/// is checked the same way.
/// </summary>
public sealed partial class RecommendedToolRow : ObservableObject
{
    public required string Key { get; init; }
    public required string Name { get; init; }
    public required string Icon { get; init; }
    public required string GitHubRepo { get; init; }
    public required Func<string, bool> AssetMatches { get; init; }

    [ObservableProperty]
    private string description = "";

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(ButtonIcon))]
    [NotifyPropertyChangedFor(nameof(IsBusy))]
    [NotifyPropertyChangedFor(nameof(IsIdle))]
    [NotifyPropertyChangedFor(nameof(IsDownloading))]
    private ToolDownloadState state = ToolDownloadState.Checking;

    [ObservableProperty]
    private double progress;

    [ObservableProperty]
    private string? installedVersion;

    [ObservableProperty]
    private string? latestVersion;

    [ObservableProperty]
    private string statusText = "";

    // Resolved by the last successful update check; consumed by the download step.
    public string? PendingAssetUrl { get; set; }
    public string? PendingAssetName { get; set; }
    public string? LocalInstallerPath { get; set; }

    public bool IsBusy => State is ToolDownloadState.Checking or ToolDownloadState.Downloading;

    public bool IsIdle => !IsBusy;

    public bool IsDownloading => State == ToolDownloadState.Downloading;

    public string ButtonIcon => State switch
    {
        ToolDownloadState.ReadyToInstall or ToolDownloadState.UpToDate => "PlayCircleOutline",
        ToolDownloadState.CheckFailed => "Refresh",
        _ => "Download",
    };
}
