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
/// Owns the story views/reactions/posting job -- same skeleton as EngagementViewModel
/// (DispatcherTimer + Start/Stop RelayCommands), since "view"/"reaction" target someone
/// else's story while "post" publishes the sender's own, with no target fields needed.
/// </summary>
public partial class StoriesViewModel : ObservableObject
{
    private readonly BackendClient _backend;
    private readonly DispatcherTimer _statusTimer;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string actionType = "view";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string targetChat = "";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private int? targetStoryId;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string reactionEmoji = "🔥";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string mediaPath = "";

    [ObservableProperty]
    private string caption = "";

    [ObservableProperty]
    private string privacy = "everyone";

    [ObservableProperty]
    private int? periodHours;

    [ObservableProperty]
    private string senderPhonesText = "";

    [ObservableProperty]
    private int streams = 1;

    [ObservableProperty]
    private double delayMinSec = 1;

    [ObservableProperty]
    private double delayMaxSec = 8;

    [ObservableProperty]
    private double maxFloodWaitSec = 120;

    [ObservableProperty]
    private int? dailyCapPerAccount;

    [ObservableProperty]
    private int? maxTotalAccounts;

    [ObservableProperty]
    private int autoStopBan;

    [ObservableProperty]
    private int autoStopSpamblock;

    [ObservableProperty]
    private int autoStopFloodWait;

    [ObservableProperty]
    private bool requireProxy;

    [ObservableProperty]
    private StoriesStatusDto? latestStatus;

    [ObservableProperty]
    private string statusMessage = "";

    public bool IsRunning => LatestStatus?.Running == true;

    public bool IsPostAction => ActionType == "post";
    public bool IsTargetedAction => !IsPostAction;
    public bool IsReactionAction => ActionType == "reaction";

    public StoriesViewModel(BackendClient backend)
    {
        _backend = backend;
        _statusTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1.5) };
        _statusTimer.Tick += async (_, _) => await RefreshStatusAsync();
        _statusTimer.Start();
    }

    partial void OnActionTypeChanged(string value)
    {
        OnPropertyChanged(nameof(IsPostAction));
        OnPropertyChanged(nameof(IsTargetedAction));
        OnPropertyChanged(nameof(IsReactionAction));
    }

    partial void OnLatestStatusChanged(StoriesStatusDto? value)
    {
        OnPropertyChanged(nameof(IsRunning));
        StartCommand.NotifyCanExecuteChanged();
        StopCommand.NotifyCanExecuteChanged();
    }

    private async Task RefreshStatusAsync()
    {
        try
        {
            LatestStatus = await _backend.GetStoriesStatusAsync();
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

    private bool CanStart() =>
        !IsRunning
        && (IsPostAction
            ? !string.IsNullOrWhiteSpace(MediaPath)
            : !string.IsNullOrWhiteSpace(TargetChat) && TargetStoryId is > 0
              && (!IsReactionAction || !string.IsNullOrWhiteSpace(ReactionEmoji)));

    [RelayCommand(CanExecute = nameof(CanStart))]
    private async Task StartAsync()
    {
        StatusMessage = "";
        try
        {
            await _backend.StartStoriesAsync(new StoriesStartRequest
            {
                ActionType = ActionType,
                TargetChat = TargetChat.Trim(),
                TargetStoryId = TargetStoryId ?? 0,
                ReactionEmoji = ReactionEmoji,
                MediaPath = MediaPath,
                Caption = Caption,
                Privacy = Privacy,
                PeriodHours = PeriodHours,
                SenderPhones = SplitEntries(SenderPhonesText),
                Streams = Math.Max(1, Streams),
                DelayMinSec = DelayMinSec,
                DelayMaxSec = DelayMaxSec,
                MaxFloodWaitSec = MaxFloodWaitSec,
                DailyCapPerAccount = DailyCapPerAccount,
                MaxTotalAccounts = MaxTotalAccounts,
                AutoStopBan = AutoStopBan,
                AutoStopSpamblock = AutoStopSpamblock,
                AutoStopFloodWait = AutoStopFloodWait,
                RequireProxy = RequireProxy,
            });
            await RefreshStatusAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }

    [RelayCommand(CanExecute = nameof(IsRunning))]
    private async Task StopAsync()
    {
        try
        {
            await _backend.StopStoriesAsync();
            await RefreshStatusAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }

    [RelayCommand]
    private void BrowseMediaPath()
    {
        var dialog = new Microsoft.Win32.OpenFileDialog
        {
            Title = LocalizationService.Instance["Stories.ChooseMediaTitle"],
            Filter = "Media files (*.jpg;*.jpeg;*.png;*.mp4;*.mov)|*.jpg;*.jpeg;*.png;*.mp4;*.mov|All files|*.*",
        };
        if (dialog.ShowDialog() == true)
            MediaPath = dialog.FileName;
    }

    private static List<string> SplitEntries(string text) =>
        text.Split(['\n', ','], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();
}
