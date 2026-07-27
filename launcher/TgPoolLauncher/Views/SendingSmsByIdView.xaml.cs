using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Net;
using System.Runtime.CompilerServices;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Media;
using System.Windows.Navigation;
using Microsoft.Win32;
using TgPoolLauncher.Models;
using TgPoolLauncher.Services;

namespace TgPoolLauncher.Views;

public partial class SendingSmsByIdView : UserControl
{
    private readonly BackendClient _backend;
    private readonly ObservableCollection<ProgramActionRow> _programActions = new();
    private readonly ObservableCollection<SelectableSenderAccount> _availableAccounts = new();
    private readonly List<string> _senderPhones = new();
    private CancellationTokenSource? _pollCancellation;
    private bool _isStarting;
    private ModalKind _activeModal;
    private string? _lastExportPath;
    private Random _random = new();

    public SendingSmsByIdView(BackendClient backend)
    {
        _backend = backend;
        InitializeComponent();
        ProgramActionsGrid.ItemsSource = _programActions;
        AccountsListBox.ItemsSource = _availableAccounts;
        ResetForm();
        Loaded += async (_, _) =>
        {
            await LoadAccountsAsync(logFailure: false);
            await RestoreJobStatusAsync();
        };
    }

    private void BoldButton_Click(object sender, RoutedEventArgs e) =>
        WrapSelection("<b>", "</b>", "bold text");

    private void ItalicButton_Click(object sender, RoutedEventArgs e) =>
        WrapSelection("<i>", "</i>", "italic text");

    private void CodeButton_Click(object sender, RoutedEventArgs e) =>
        WrapSelection("<code>", "</code>", "code");

    private void LinkButton_Click(object sender, RoutedEventArgs e) =>
        InsertAtCaret("<a href=\"https://\">link text</a>");

    private void UsernameButton_Click(object sender, RoutedEventArgs e) =>
        InsertAtCaret("{username}");

    private void RandomizerButton_Click(object sender, RoutedEventArgs e)
    {
        _random = new Random();
        UpdatePreview();
        AddAction("Preview", "Generated a new text variation.");
    }

    private void ForwardButton_Click(object sender, RoutedEventArgs e) =>
        ShowModal(
            ModalKind.Forward,
            "Enter link(s) to post in channel",
            "Add one Telegram post link per line.");

    private void AttachFileButton_Click(object sender, RoutedEventArgs e) =>
        ShowModal(
            ModalKind.File,
            "Add file",
            "Choose one or more local files, or enter direct file links.");

    private void PostbotButton_Click(object sender, RoutedEventArgs e) =>
        ShowModal(
            ModalKind.Postbot,
            "Repost via Postbot",
            "Enter the bot username and one or more post IDs.");

    private void ClearMessageButton_Click(object sender, RoutedEventArgs e)
    {
        MessageTextBox.Clear();
        ForwardLinksTextBox.Clear();
        AttachmentLinkTextBox.Clear();
        PostbotNameTextBox.Text = "@postbot";
        PostbotIdsTextBox.Clear();
        UpdateMessageSource();
    }

    private void MessageTextBox_TextChanged(object sender, TextChangedEventArgs e) => UpdatePreview();

    private void BrowseDatabaseButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Select Telegram user ID database",
            Filter = "Audience databases|*.txt;*.csv;*.xlsx;*.xls;*.json|All files|*.*",
            CheckFileExists = true,
        };
        if (dialog.ShowDialog() == true)
        {
            DatabasePathTextBox.Text = dialog.FileName;
            AddAction("Database", $"Selected {Path.GetFileName(dialog.FileName)}.");
        }
    }

    private async void SelectAccountsButton_Click(object sender, RoutedEventArgs e)
    {
        await LoadAccountsAsync(logFailure: true);
        if (_availableAccounts.Count == 0)
            return;
        ShowModal(
            ModalKind.Accounts,
            "Select sender accounts",
            "Only checked accounts will be used for this job.");
    }

    private void ResetButton_Click(object sender, RoutedEventArgs e) => ResetForm();

    private async void StartButton_Click(object sender, RoutedEventArgs e)
    {
        if (_isStarting || !StartButton.IsEnabled)
            return;

        if (string.IsNullOrWhiteSpace(DatabasePathTextBox.Text))
        {
            AddAction("Sending SMS by ID", "Select a user ID database before starting.");
            return;
        }
        if (_senderPhones.Count == 0)
        {
            AddAction("Sending SMS by ID", "Select at least one sender account.");
            return;
        }

        DateTimeOffset? scheduleAt = null;
        if (SendingByTimeToggle.IsChecked == true)
        {
            if (!TryParseSchedule(ScheduleAtTextBox.Text, out scheduleAt))
            {
                AddAction("Sending SMS by ID", "Enter a future local time as yyyy-MM-dd HH:mm.");
                return;
            }
        }

        var request = new SendByIdStartRequest
        {
            DatabasePath = DatabasePathTextBox.Text.Trim(),
            Message = MessageTextBox.Text,
            SenderPhones = [.. _senderPhones],
            MediaPaths = NonEmptyLines(AttachmentLinkTextBox.Text),
            ForwardLinks = NonEmptyLines(ForwardLinksTextBox.Text),
            BotRelayUsername = PostbotNameTextBox.Text.Trim(),
            BotRelayMessageIds = ParsePositiveInts(PostbotIdsTextBox.Text),
            SmsPerAccountMin = ParsePositiveInt(SmsMinTextBox.Text, 1),
            SmsPerAccountMax = ParsePositiveInt(SmsMaxTextBox.Text, 40),
            DelayMinSec = ParseNonNegativeDouble(DelayMinTextBox.Text, 1),
            DelayMaxSec = ParseNonNegativeDouble(DelayMaxTextBox.Text, 10),
            MaxFloodWaitSec = ParseNonNegativeDouble(FloodWaitTextBox.Text, 500),
            DeleteDialog = DeleteDialogToggle.IsChecked == true,
            LinkPreview = PreviewLinksToggle.IsChecked == true,
            Silent = SilentModeToggle.IsChecked == true,
            AutoRepost = AutoRepostToggle.IsChecked == true,
            LeaveDonorGroups = LeaveDonorGroupsToggle.IsChecked == true,
            PinMessage = PinMessageToggle.IsChecked == true,
            VideoNote = VideoCircleToggle.IsChecked == true,
            SelfDestructSec = SelfDestructToggle.IsChecked == true ? 60 : null,
            ScheduleAt = scheduleAt,
            Streams = StreamsControlToggle.IsChecked == true
                ? ParsePositiveInt(StreamsTextBox.Text, 1)
                : 1,
            AutoStopBan = AutoStopToggle.IsChecked == true
                ? ParsePositiveInt(AutoStopBanTextBox.Text, 0)
                : 0,
            AutoStopSpamblock = AutoStopToggle.IsChecked == true
                ? ParsePositiveInt(AutoStopSpamblockTextBox.Text, 0)
                : 0,
            AutoStopFloodWait = AutoStopToggle.IsChecked == true
                ? ParsePositiveInt(AutoStopFloodWaitTextBox.Text, 0)
                : 0,
            RepeatEveryHours = RunControlToggle.IsChecked == true
                ? ParsePositiveDouble(RepeatHoursTextBox.Text, 1)
                : null,
            ResultsDir = AppPaths.Exports,
        };

        if (string.IsNullOrWhiteSpace(request.Message)
            && request.MediaPaths.Count == 0
            && request.ForwardLinks.Count == 0
            && request.BotRelayMessageIds.Count == 0)
        {
            AddAction("Sending SMS by ID", "Add message text, media, a repost link, or a Postbot post.");
            return;
        }

        _pollCancellation?.Cancel();
        _pollCancellation = new CancellationTokenSource();
        var ct = _pollCancellation.Token;
        _programActions.Clear();
        ResultsSummaryText.Text = "Starting...";
        _isStarting = true;
        SetRunningState(true);
        try
        {
            var response = await _backend.StartSendByIdAsync(request, ct);
            AddAction("Sending SMS by ID", $"Started job {response.JobId}.");
            await PollStatusAsync(ct);
        }
        catch (OperationCanceledException)
        {
            AddAction("Sending SMS by ID", "Status polling stopped.");
        }
        catch (Exception ex)
        {
            AddAction("Sending SMS by ID", CleanApiError(ex.Message));
            ResultsSummaryText.Text = "Could not start";
            SetRunningState(false);
        }
        finally
        {
            _isStarting = false;
        }
    }

    private async void StopButton_Click(object sender, RoutedEventArgs e)
    {
        StopButton.IsEnabled = false;
        _pollCancellation?.Cancel();
        try
        {
            await _backend.StopSendByIdAsync();
            AddAction("Sending SMS by ID", "Stop completed.");
            var status = await _backend.GetSendByIdStatusAsync();
            ApplyStatus(status);
        }
        catch (Exception ex)
        {
            AddAction("Sending SMS by ID", $"Stop failed: {CleanApiError(ex.Message)}");
            StopButton.IsEnabled = true;
        }
    }

    private void ClearActionsButton_Click(object sender, RoutedEventArgs e) => _programActions.Clear();

    private void OpenResultsButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var target = !string.IsNullOrWhiteSpace(_lastExportPath) && File.Exists(_lastExportPath)
                ? _lastExportPath
                : AppPaths.Exports;
            Directory.CreateDirectory(AppPaths.Exports);
            Process.Start(new ProcessStartInfo(target) { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            AddAction("Results", $"Could not open results: {ex.Message}");
        }
    }

    private void CloseModalButton_Click(object sender, RoutedEventArgs e) => CloseModal();

    private void ModalApplyButton_Click(object sender, RoutedEventArgs e)
    {
        switch (_activeModal)
        {
            case ModalKind.Forward:
                AddAction("Repost", DescribeCount(NonEmptyLines(ForwardLinksTextBox.Text).Count, "post link"));
                break;
            case ModalKind.File:
                AddAction("Attachment", DescribeCount(NonEmptyLines(AttachmentLinkTextBox.Text).Count, "file"));
                break;
            case ModalKind.Postbot:
                AddAction("Postbot", DescribeCount(ParsePositiveInts(PostbotIdsTextBox.Text).Count, "post ID"));
                break;
            case ModalKind.Accounts:
                _senderPhones.Clear();
                _senderPhones.AddRange(
                    _availableAccounts.Where(item => item.IsSelected).Select(item => item.Phone));
                SelectedAccountsTextBox.Text = _senderPhones.Count.ToString(CultureInfo.InvariantCulture);
                AddAction("Accounts", $"Selected {_senderPhones.Count} sender account(s).");
                break;
        }

        UpdateMessageSource();
        CloseModal();
    }

    private void ChooseLocalFileButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Select attachment",
            Filter = "Supported files|*.jpg;*.jpeg;*.png;*.gif;*.mp4;*.mov;*.ogg;*.mp3;*.wav;*.pdf;*.zip;*.doc;*.docx;*.xls;*.xlsx|All files|*.*",
            CheckFileExists = true,
            Multiselect = true,
        };
        if (dialog.ShowDialog() == true)
            AttachmentLinkTextBox.Text = string.Join(Environment.NewLine, dialog.FileNames);
    }

    private void ShowModal(ModalKind kind, string title, string subtitle)
    {
        _activeModal = kind;
        ModalTitleText.Text = title;
        ModalSubtitleText.Text = subtitle;
        ForwardModalPanel.Visibility = kind == ModalKind.Forward ? Visibility.Visible : Visibility.Collapsed;
        FileModalPanel.Visibility = kind == ModalKind.File ? Visibility.Visible : Visibility.Collapsed;
        PostbotModalPanel.Visibility = kind == ModalKind.Postbot ? Visibility.Visible : Visibility.Collapsed;
        AccountsModalPanel.Visibility = kind == ModalKind.Accounts ? Visibility.Visible : Visibility.Collapsed;
        ModalApplyButton.Content = kind == ModalKind.Accounts ? "Use selected accounts" : "Apply";
        ModalOverlay.Visibility = Visibility.Visible;
    }

    private void CloseModal() => ModalOverlay.Visibility = Visibility.Collapsed;

    private void ResetForm()
    {
        MessageTextBox.Text = "";
        DatabasePathTextBox.Text = "";
        SmsMinTextBox.Text = "min  1";
        SmsMaxTextBox.Text = "max  40";
        DelayMinTextBox.Text = "min  1";
        DelayMaxTextBox.Text = "max  10";
        FloodWaitTextBox.Text = "500 sec";
        SelectedAccountsTextBox.Text = _senderPhones.Count.ToString(CultureInfo.InvariantCulture);
        DeleteDialogToggle.IsChecked = false;
        PreviewLinksToggle.IsChecked = true;
        SilentModeToggle.IsChecked = false;
        AutoRepostToggle.IsChecked = false;
        LeaveDonorGroupsToggle.IsChecked = true;
        PinMessageToggle.IsChecked = false;
        VideoCircleToggle.IsChecked = false;
        SelfDestructToggle.IsChecked = false;
        SendingByTimeToggle.IsChecked = false;
        StreamsControlToggle.IsChecked = false;
        AutoStopToggle.IsChecked = false;
        RunControlToggle.IsChecked = false;
        ScheduleAtTextBox.Text = DateTime.Now.AddHours(1).ToString("yyyy-MM-dd HH:mm");
        StreamsTextBox.Text = "4";
        AutoStopBanTextBox.Text = "1";
        AutoStopSpamblockTextBox.Text = "1";
        AutoStopFloodWaitTextBox.Text = "3";
        RepeatHoursTextBox.Text = "1";
        ForwardLinksTextBox.Text = "";
        AttachmentLinkTextBox.Text = "";
        PostbotNameTextBox.Text = "@postbot";
        PostbotIdsTextBox.Text = "";
        _lastExportPath = null;
        ResultsSummaryText.Text = "No results yet";
        UpdatePreview();
        UpdateMessageSource();
    }

    private async Task LoadAccountsAsync(bool logFailure)
    {
        try
        {
            var accounts = await _backend.GetAccountsAsync();
            var selected = _senderPhones.ToHashSet(StringComparer.OrdinalIgnoreCase);
            _availableAccounts.Clear();
            foreach (var account in accounts.Where(IsUsableSender))
            {
                _availableAccounts.Add(new SelectableSenderAccount(
                    account.Phone,
                    BuildAccountDetail(account),
                    selected.Count == 0 || selected.Contains(account.Phone)));
            }

            if (_senderPhones.Count == 0)
            {
                _senderPhones.AddRange(_availableAccounts.Where(item => item.IsSelected).Select(item => item.Phone));
            }
            SelectedAccountsTextBox.Text = _senderPhones.Count.ToString(CultureInfo.InvariantCulture);
        }
        catch (Exception ex)
        {
            if (logFailure)
                AddAction("Accounts", $"Could not load accounts: {CleanApiError(ex.Message)}");
        }
    }

    private async Task PollStatusAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            var status = await _backend.GetSendByIdStatusAsync(ct);
            ApplyStatus(status);
            if (status.Finished || (!status.Running && status.JobId is null))
                return;
            await Task.Delay(1000, ct);
        }
    }

    private void ApplyStatus(SendByIdStatusDto status)
    {
        SetRunningState(status.Running);
        _programActions.Clear();
        foreach (var result in status.Results.AsEnumerable().Reverse())
        {
            var identity = string.IsNullOrWhiteSpace(result.SenderPhone)
                ? result.RecipientId.ToString(CultureInfo.InvariantCulture)
                : result.SenderPhone;
            _programActions.Add(new ProgramActionRow(
                $"C{result.Cycle}",
                identity,
                $"{result.State}: ID {result.RecipientId} - {result.Message}"));
        }

        ResultsSummaryText.Text =
            $"Cycle {status.Cycle}  |  Sent {status.Sent}  |  Failed {status.Failed}  |  "
            + $"BAN {status.BanCount}  |  SpamBlock {status.SpamblockCount}  |  FloodWait {status.FloodWaitCount}";
        _lastExportPath = status.ExportPath;
        if (status.Finished)
        {
            AddAction(
                "Sending SMS by ID",
                string.IsNullOrWhiteSpace(status.Error)
                    ? $"Finished: sent {status.Sent}, failed {status.Failed}."
                    : $"Finished with error: {status.Error}");
        }
    }

    private async Task RestoreJobStatusAsync()
    {
        try
        {
            var status = await _backend.GetSendByIdStatusAsync();
            ApplyStatus(status);
            if (!status.Running)
                return;

            _pollCancellation?.Cancel();
            _pollCancellation = new CancellationTokenSource();
            await PollStatusAsync(_pollCancellation.Token);
        }
        catch (OperationCanceledException)
        {
        }
        catch (Exception ex)
        {
            AddAction("Sending SMS by ID", $"Could not restore job status: {CleanApiError(ex.Message)}");
            SetRunningState(false);
        }
    }

    private void SetRunningState(bool running)
    {
        StartButton.IsEnabled = !running;
        StopButton.IsEnabled = running;
    }

    private void UpdatePreview()
    {
        if (PreviewTextBlock is null)
            return;

        PreviewTextBlock.Inlines.Clear();
        if (string.IsNullOrWhiteSpace(MessageTextBox.Text))
        {
            PreviewTextBlock.Inlines.Add(new Run("Message preview will appear here.")
            {
                Foreground = (Brush)FindResource("TextFaintBrush"),
            });
            return;
        }

        RenderPreviewInlines(ResolveSpintax(MessageTextBox.Text));
    }

    private void UpdateMessageSource()
    {
        if (MessageSourceText is null)
            return;

        var parts = new List<string>();
        var forwardCount = NonEmptyLines(ForwardLinksTextBox.Text).Count;
        var files = NonEmptyLines(AttachmentLinkTextBox.Text);
        var postbotCount = ParsePositiveInts(PostbotIdsTextBox.Text).Count;
        if (forwardCount > 0)
            parts.Add($"{forwardCount} repost link(s)");
        if (files.Count > 0)
            parts.Add(files.Count == 1 ? $"attachment: {Path.GetFileName(files[0])}" : $"{files.Count} attachments");
        if (postbotCount > 0)
            parts.Add($"{postbotCount} Postbot post(s)");

        MessageSourceText.Text = string.Join("  |  ", parts);
        MessageSourceText.Visibility = parts.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
    }

    private void WrapSelection(string prefix, string suffix, string placeholder)
    {
        var start = MessageTextBox.SelectionStart;
        var length = MessageTextBox.SelectionLength;
        var inner = length > 0 ? MessageTextBox.SelectedText : placeholder;
        MessageTextBox.Text =
            MessageTextBox.Text[..start] + prefix + inner + suffix + MessageTextBox.Text[(start + length)..];
        MessageTextBox.Focus();
        MessageTextBox.SelectionStart = start + prefix.Length;
        MessageTextBox.SelectionLength = inner.Length;
    }

    private void InsertAtCaret(string text)
    {
        var start = MessageTextBox.SelectionStart;
        MessageTextBox.Text =
            MessageTextBox.Text[..start] + text + MessageTextBox.Text[(start + MessageTextBox.SelectionLength)..];
        MessageTextBox.Focus();
        MessageTextBox.SelectionStart = start + text.Length;
    }

    private void AddAction(string account, string message) =>
        _programActions.Insert(0, new ProgramActionRow(
            DateTime.Now.ToString("HH:mm:ss"),
            account,
            message));

    private string ResolveSpintax(string value)
    {
        var result = value;
        var expression = new Regex(@"\{([^{}|]+\|[^{}]+)\}");
        for (var iteration = 0; iteration < 20; iteration++)
        {
            var match = expression.Match(result);
            if (!match.Success)
                break;
            var options = match.Groups[1].Value.Split('|');
            result = result[..match.Index]
                + options[_random.Next(options.Length)]
                + result[(match.Index + match.Length)..];
        }
        return result;
    }

    private void RenderPreviewInlines(string markup)
    {
        var tokenPattern = new Regex(
            "(</?(?:b|i|code)>|<a\\s+href=\"([^\"]*)\">|</a>)",
            RegexOptions.IgnoreCase);
        var bold = false;
        var italic = false;
        var code = false;
        string? link = null;
        var offset = 0;

        foreach (Match token in tokenPattern.Matches(markup))
        {
            AddPreviewText(markup[offset..token.Index], bold, italic, code, link);
            var tag = token.Value.ToLowerInvariant();
            switch (tag)
            {
                case "<b>":
                    bold = true;
                    break;
                case "</b>":
                    bold = false;
                    break;
                case "<i>":
                    italic = true;
                    break;
                case "</i>":
                    italic = false;
                    break;
                case "<code>":
                    code = true;
                    break;
                case "</code>":
                    code = false;
                    break;
                case "</a>":
                    link = null;
                    break;
                default:
                    if (tag.StartsWith("<a ", StringComparison.Ordinal))
                        link = token.Groups[2].Value;
                    break;
            }
            offset = token.Index + token.Length;
        }
        AddPreviewText(markup[offset..], bold, italic, code, link);
    }

    private void AddPreviewText(
        string raw,
        bool bold,
        bool italic,
        bool code,
        string? link)
    {
        var lines = WebUtility.HtmlDecode(raw).Replace("\r\n", "\n").Split('\n');
        for (var index = 0; index < lines.Length; index++)
        {
            if (lines[index].Length > 0)
            {
                var run = new Run(lines[index])
                {
                    FontWeight = bold ? FontWeights.Bold : FontWeights.Normal,
                    FontStyle = italic ? FontStyles.Italic : FontStyles.Normal,
                    FontFamily = code ? new FontFamily("Consolas") : FontFamily,
                    Background = code ? (Brush)FindResource("SurfaceHoverBrush") : Brushes.Transparent,
                };
                if (Uri.TryCreate(link, UriKind.Absolute, out var uri))
                {
                    var hyperlink = new Hyperlink(run)
                    {
                        NavigateUri = uri,
                        Foreground = (Brush)FindResource("AccentHoverBrush"),
                        TextDecorations = TextDecorations.Underline,
                    };
                    hyperlink.RequestNavigate += PreviewLink_RequestNavigate;
                    PreviewTextBlock.Inlines.Add(hyperlink);
                }
                else
                {
                    PreviewTextBlock.Inlines.Add(run);
                }
            }
            if (index < lines.Length - 1)
                PreviewTextBlock.Inlines.Add(new LineBreak());
        }
    }

    private static void PreviewLink_RequestNavigate(object sender, RequestNavigateEventArgs e)
    {
        try
        {
            Process.Start(new ProcessStartInfo(e.Uri.AbsoluteUri) { UseShellExecute = true });
        }
        catch
        {
            // Preview links are optional; a missing browser association must not close the app.
        }
        e.Handled = true;
    }

    private static List<string> NonEmptyLines(string value) =>
        value.Split(["\r\n", "\n"], StringSplitOptions.RemoveEmptyEntries)
            .Select(line => line.Trim())
            .Where(line => line.Length > 0)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();

    private static List<int> ParsePositiveInts(string value) =>
        Regex.Matches(value, @"\d+")
            .Select(match => int.TryParse(match.Value, out var number) ? number : 0)
            .Where(number => number > 0)
            .Distinct()
            .ToList();

    private static int ParsePositiveInt(string? raw, int fallback)
    {
        var match = Regex.Match(raw ?? "", @"\d+");
        return match.Success && int.TryParse(match.Value, out var value) && value > 0
            ? value
            : fallback;
    }

    private static double ParseNonNegativeDouble(string? raw, double fallback)
    {
        var match = Regex.Match(raw ?? "", @"\d+(?:[.,]\d+)?");
        return match.Success
               && double.TryParse(
                   match.Value.Replace(',', '.'),
                   NumberStyles.Float,
                   CultureInfo.InvariantCulture,
                   out var value)
               && value >= 0
            ? value
            : fallback;
    }

    private static double ParsePositiveDouble(string? raw, double fallback)
    {
        var value = ParseNonNegativeDouble(raw, fallback);
        return value > 0 ? value : fallback;
    }

    private static bool TryParseSchedule(string raw, out DateTimeOffset? schedule)
    {
        schedule = null;
        if (!DateTime.TryParseExact(
                raw.Trim(),
                "yyyy-MM-dd HH:mm",
                CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeLocal,
                out var local)
            || local <= DateTime.Now)
        {
            return false;
        }
        schedule = new DateTimeOffset(local);
        return true;
    }

    private static bool IsUsableSender(AccountDto account)
    {
        var blocked = new[] { "banned", "unauthorized", "spamblock", "frozen" };
        return !string.IsNullOrWhiteSpace(account.Phone)
               && !blocked.Contains(account.Status, StringComparer.OrdinalIgnoreCase);
    }

    private static string BuildAccountDetail(AccountDto account)
    {
        var parts = new[] { account.Status, account.Country, account.Folder }
            .Where(value => !string.IsNullOrWhiteSpace(value));
        return string.Join("  |  ", parts);
    }

    private static string DescribeCount(int count, string noun) =>
        count == 0 ? $"{noun} cleared." : $"Added {count} {noun}{(count == 1 ? "" : "s")}.";

    private static string CleanApiError(string value)
    {
        var detail = Regex.Match(value, "\"detail\"\\s*:\\s*\"([^\"]+)\"");
        return detail.Success ? detail.Groups[1].Value : value;
    }

    private enum ModalKind
    {
        Forward,
        File,
        Postbot,
        Accounts,
    }

    private sealed class SelectableSenderAccount : INotifyPropertyChanged
    {
        private bool _isSelected;

        public SelectableSenderAccount(string phone, string detail, bool isSelected)
        {
            Phone = phone;
            Detail = detail;
            _isSelected = isSelected;
        }

        public string Phone { get; }
        public string Detail { get; }

        public bool IsSelected
        {
            get => _isSelected;
            set
            {
                if (_isSelected == value)
                    return;
                _isSelected = value;
                PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(IsSelected)));
            }
        }

        public event PropertyChangedEventHandler? PropertyChanged;
    }

    private sealed class ProgramActionRow : INotifyPropertyChanged
    {
        private string _time;
        private string _account;
        private string _message;

        public ProgramActionRow(string time, string account, string message)
        {
            _time = time;
            _account = account;
            _message = message;
        }

        public string Time
        {
            get => _time;
            set
            {
                if (_time == value)
                    return;
                _time = value;
                OnPropertyChanged();
            }
        }

        public string Account
        {
            get => _account;
            set
            {
                if (_account == value)
                    return;
                _account = value;
                OnPropertyChanged();
            }
        }

        public string Message
        {
            get => _message;
            set
            {
                if (_message == value)
                    return;
                _message = value;
                OnPropertyChanged();
            }
        }

        public event PropertyChangedEventHandler? PropertyChanged;

        private void OnPropertyChanged([CallerMemberName] string? propertyName = null) =>
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }
}
