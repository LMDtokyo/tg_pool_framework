using System.Collections.ObjectModel;
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
/// Creates and manages restart-durable scheduled campaigns (/scheduled_campaigns).
/// A schedule wraps a minimal send-by-ID or send-by-numbers payload -- every other
/// SendByIdStartRequest/SendByNumbersStartRequest field keeps its backend default,
/// matching a "quick schedule" rather than duplicating the full send screens.
/// </summary>
public partial class ScheduledCampaignsViewModel : ObservableObject
{
    private readonly BackendClient _backend;
    private readonly DispatcherTimer _refreshTimer;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(CreateCommand))]
    private string name = "";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(CreateCommand))]
    private bool isSendByNumbers;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(CreateCommand))]
    private string databasePath = "";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(CreateCommand))]
    private string phoneNumbersText = "";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(CreateCommand))]
    private string message = "";

    [ObservableProperty]
    private DateTime startDate = DateTime.Today.AddDays(1);

    [ObservableProperty]
    private string startTimeText = "09:00";

    [ObservableProperty]
    private string? repeatIntervalHoursText;

    [ObservableProperty]
    private string? maxOccurrencesText;

    [ObservableProperty]
    private string statusMessage = "";

    public ObservableCollection<ScheduledCampaignDto> Campaigns { get; } = new();

    public ScheduledCampaignsViewModel(BackendClient backend)
    {
        _backend = backend;
        _refreshTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(5) };
        _refreshTimer.Tick += async (_, _) => await RefreshAsync();
        _refreshTimer.Start();
        _ = RefreshAsync();
    }

    private async Task RefreshAsync()
    {
        try
        {
            var campaigns = await _backend.GetScheduledCampaignsAsync();
            Campaigns.Clear();
            foreach (var campaign in campaigns.OrderBy(c => c.NextRunAt))
                Campaigns.Add(campaign);
        }
        catch (HttpRequestException)
        {
            // backend momentarily unreachable -- keep the last known list
        }
        catch (TaskCanceledException)
        {
            // request timed out/was aborted (e.g. backend restarting) -- same as above
        }
    }

    private bool CanCreate() =>
        !string.IsNullOrWhiteSpace(Name)
        && !string.IsNullOrWhiteSpace(Message)
        && (IsSendByNumbers
            ? !string.IsNullOrWhiteSpace(PhoneNumbersText)
            : !string.IsNullOrWhiteSpace(DatabasePath));

    [RelayCommand(CanExecute = nameof(CanCreate))]
    private async Task CreateAsync()
    {
        StatusMessage = "";
        if (!TimeSpan.TryParse(StartTimeText, out var timeOfDay))
        {
            StatusMessage = LocalizationService.Instance["ScheduledCampaigns.InvalidTimeError"];
            return;
        }
        var startAt = new DateTimeOffset(StartDate.Date + timeOfDay, DateTimeOffset.Now.Offset);

        double? repeatHours = null;
        if (!string.IsNullOrWhiteSpace(RepeatIntervalHoursText))
        {
            if (!double.TryParse(RepeatIntervalHoursText, out var parsedHours) || parsedHours <= 0)
            {
                StatusMessage = LocalizationService.Instance["ScheduledCampaigns.InvalidRepeatError"];
                return;
            }
            repeatHours = parsedHours;
        }

        int? maxOccurrences = null;
        if (!string.IsNullOrWhiteSpace(MaxOccurrencesText))
        {
            if (!int.TryParse(MaxOccurrencesText, out var parsedCount) || parsedCount < 1)
            {
                StatusMessage = LocalizationService.Instance["ScheduledCampaigns.InvalidMaxOccurrencesError"];
                return;
            }
            maxOccurrences = parsedCount;
        }

        var request = IsSendByNumbers
            ? new ScheduledCampaignCreateRequest
            {
                Name = Name,
                CampaignType = "send_by_numbers",
                SendByNumbers = new SendByNumbersStartRequest
                {
                    PhoneNumbers = SplitEntries(PhoneNumbersText),
                    Message = Message,
                },
                StartAt = startAt,
                RepeatIntervalHours = repeatHours,
                MaxOccurrences = maxOccurrences,
            }
            : new ScheduledCampaignCreateRequest
            {
                Name = Name,
                CampaignType = "send_by_id",
                SendById = new SendByIdStartRequest
                {
                    DatabasePath = DatabasePath,
                    Message = Message,
                },
                StartAt = startAt,
                RepeatIntervalHours = repeatHours,
                MaxOccurrences = maxOccurrences,
            };

        try
        {
            await _backend.CreateScheduledCampaignAsync(request);
            Name = "";
            Message = "";
            DatabasePath = "";
            PhoneNumbersText = "";
            RepeatIntervalHoursText = null;
            MaxOccurrencesText = null;
            await RefreshAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }

    private static List<string> SplitEntries(string text) =>
        text.Split(['\n', ','], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();

    [RelayCommand]
    private void BrowseDatabasePath()
    {
        var dialog = new Microsoft.Win32.OpenFileDialog
        {
            Title = LocalizationService.Instance["ScheduledCampaigns.ChooseDatabaseTitle"],
            Filter = "Audience files (*.txt;*.csv;*.json;*.xlsx;*.xls)|*.txt;*.csv;*.json;*.xlsx;*.xls|All files|*.*",
        };
        if (dialog.ShowDialog() == true)
            DatabasePath = dialog.FileName;
    }

    [RelayCommand]
    private async Task CancelAsync(ScheduledCampaignDto campaign)
    {
        try
        {
            await _backend.CancelScheduledCampaignAsync(campaign.Id);
            await RefreshAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }

    [RelayCommand]
    private async Task DeleteAsync(ScheduledCampaignDto campaign)
    {
        try
        {
            await _backend.DeleteScheduledCampaignAsync(campaign.Id);
            await RefreshAsync();
        }
        catch (Exception ex)
        {
            StatusMessage = ex.Message;
        }
    }
}
