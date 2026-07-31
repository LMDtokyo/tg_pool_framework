using System.Linq;
using System.Net.Http;
using System.Windows.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using TgPoolLauncher.Models;
using TgPoolLauncher.Services;

namespace TgPoolLauncher.ViewModels;

/// <summary>
/// Owns the reactions/views/poll-votes/comments ("engagement") job: one target post,
/// each participating account acts on it exactly once. Same skeleton as ParsingViewModel
/// (DispatcherTimer + Start/Stop RelayCommands) -- the job itself supports graceful
/// cancellation via the shared PoolAccessGuard/shutdown_event.
/// </summary>
public partial class EngagementViewModel : ObservableObject
{
    private readonly BackendClient _backend;
    private readonly DispatcherTimer _statusTimer;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string actionType = "reaction";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string targetChat = "";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private int? targetMessageId;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string reactionEmoji = "❤️";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private int? pollOptionIndex;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(StartCommand))]
    private string commentText = "";

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
    private bool requireProxy = true;

    [ObservableProperty]
    private EngagementStatusDto? latestStatus;

    [ObservableProperty]
    private string statusMessage = "";

    public bool IsRunning => LatestStatus?.Running == true;

    public bool IsReactionAction => ActionType == "reaction";
    public bool IsPollVoteAction => ActionType == "poll_vote";
    public bool IsCommentAction => ActionType == "comment";

    public EngagementViewModel(BackendClient backend)
    {
        _backend = backend;
        _statusTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1.5) };
        _statusTimer.Tick += async (_, _) => await RefreshStatusAsync();
        _statusTimer.Start();
    }

    partial void OnActionTypeChanged(string value)
    {
        OnPropertyChanged(nameof(IsReactionAction));
        OnPropertyChanged(nameof(IsPollVoteAction));
        OnPropertyChanged(nameof(IsCommentAction));
    }

    partial void OnLatestStatusChanged(EngagementStatusDto? value)
    {
        OnPropertyChanged(nameof(IsRunning));
        StartCommand.NotifyCanExecuteChanged();
        StopCommand.NotifyCanExecuteChanged();
    }

    private async Task RefreshStatusAsync()
    {
        try
        {
            LatestStatus = await _backend.GetEngagementStatusAsync();
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
        && !string.IsNullOrWhiteSpace(TargetChat)
        && TargetMessageId is > 0
        && (!IsReactionAction || !string.IsNullOrWhiteSpace(ReactionEmoji))
        && (!IsPollVoteAction || PollOptionIndex is >= 0)
        && (!IsCommentAction || !string.IsNullOrWhiteSpace(CommentText));

    [RelayCommand(CanExecute = nameof(CanStart))]
    private async Task StartAsync()
    {
        StatusMessage = "";
        try
        {
            await _backend.StartEngagementAsync(new EngagementStartRequest
            {
                ActionType = ActionType,
                TargetChat = TargetChat.Trim(),
                TargetMessageId = TargetMessageId ?? 0,
                ReactionEmoji = ReactionEmoji,
                PollOptionIndex = PollOptionIndex,
                CommentText = CommentText,
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
            await _backend.StopEngagementAsync();
            await RefreshStatusAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }

    private static List<string> SplitEntries(string text) =>
        text.Split(['\n', ','], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();
}
