using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Globalization;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using TgPoolLauncher.Models;
using TgPoolLauncher.Services;

namespace TgPoolLauncher.Views;

public partial class SendByNumbersView : UserControl
{
    private const string PhoneNumbersPlaceholder =
        "List of phone numbers, each one from a new line, in any format:\n" +
        "1 (222) 333 4455\n" +
        "1 222 333 4455\n" +
        "1-222-333-4455\n" +
        "12223334455\n\n" +
        "The program will automatically remove all extra spaces, brackets, hyphens, and add to the database in the correct format.\n\n" +
        "If the work was interrupted in the process, the module is restarted with the database that was created during the previous run.\n" +
        "It allows you to pick up from where you left off.\n\n" +
        "See the video on the main page for more details.";

    private readonly BackendClient _backend;
    private readonly ObservableCollection<ProgramActionRow> _programActions = new();
    private readonly List<string> _senderPhones = new();
    private CancellationTokenSource? _pollCancellation;

    public SendByNumbersView(BackendClient backend)
    {
        _backend = backend;
        InitializeComponent();
        ProgramActionsGrid.ItemsSource = _programActions;
        ResetForm();
        Loaded += async (_, _) => await LoadAccountsAsync();
    }

    private void BoldButton_Click(object sender, RoutedEventArgs e) => WrapSelection("<b>", "</b>", "bold text");

    private void ItalicButton_Click(object sender, RoutedEventArgs e) => WrapSelection("<i>", "</i>", "italic text");

    private void CodeButton_Click(object sender, RoutedEventArgs e) => WrapSelection("<code>", "</code>", "code");

    private void LinkButton_Click(object sender, RoutedEventArgs e) => InsertAtCaret("<a href=\"https://\">link text</a>");

    private void PlaceholderButton_Click(object sender, RoutedEventArgs e) => InsertAtCaret("{first_name}");

    private void ClearMessageButton_Click(object sender, RoutedEventArgs e)
    {
        MessageTextBox.Text = "";
        UpdatePreview();
    }

    private void MessageTextBox_TextChanged(object sender, TextChangedEventArgs e) => UpdatePreview();

    private void PhoneNumbersTextBox_TextChanged(object sender, TextChangedEventArgs e) => UpdatePhoneNumbersHeader();

    private void ClearPhoneNumbersButton_Click(object sender, RoutedEventArgs e)
    {
        PhoneNumbersTextBox.Text = PhoneNumbersPlaceholder;
        UpdatePhoneNumbersHeader();
    }

    private void ResetButton_Click(object sender, RoutedEventArgs e) => ResetForm();

    private async void SelectAccountsButton_Click(object sender, RoutedEventArgs e)
    {
        await LoadAccountsAsync();
        AddAction("Accounts", $"Selected {_senderPhones.Count} saved sender account(s).");
    }

    private void OpenResultsButton_Click(object sender, RoutedEventArgs e) =>
        AddAction("Results", "Results folder is not connected yet.");

    private async void StartButton_Click(object sender, RoutedEventArgs e)
    {
        var phones = ParsePhoneNumbers(PhoneNumbersTextBox.Text);
        if (string.IsNullOrWhiteSpace(MessageTextBox.Text))
        {
            AddAction("Send by numbers", "Add message text before starting.");
            return;
        }

        if (phones.Count == 0)
        {
            AddAction("Send by numbers", "Add at least one phone number before starting.");
            return;
        }

        if (_senderPhones.Count == 0)
            await LoadAccountsAsync();
        if (_senderPhones.Count == 0)
        {
            AddAction("Send by numbers", "No saved sender accounts are available.");
            return;
        }

        _pollCancellation?.Cancel();
        _pollCancellation = new CancellationTokenSource();
        var ct = _pollCancellation.Token;
        _programActions.Clear();
        foreach (var phone in phones)
            _programActions.Add(new ProgramActionRow(DateTime.Now.ToString("HH:mm:ss"), phone, "Queued"));

        try
        {
            var response = await _backend.StartSendByNumbersAsync(new SendByNumbersStartRequest
            {
                PhoneNumbers = phones,
                Message = MessageTextBox.Text,
                SenderPhones = _senderPhones,
                SmsPerAccountMin = ParsePositiveInt(SmsMinTextBox.Text, 1),
                SmsPerAccountMax = ParsePositiveInt(SmsMaxTextBox.Text, 40),
                DelayMinSec = ParseNonNegativeDouble(DelayMinTextBox.Text, 1),
                DelayMaxSec = ParseNonNegativeDouble(DelayMaxTextBox.Text, 10),
                MaxFloodWaitSec = ParseNonNegativeDouble(FloodWaitTextBox.Text, 500),
                LinkPreview = true,
            }, ct);
            AddAction("Send by numbers", $"Started job {response.JobId}");
            await PollStatusAsync(ct);
        }
        catch (OperationCanceledException)
        {
            AddAction("Send by numbers", "Stopped.");
        }
        catch (Exception ex)
        {
            AddAction("Send by numbers", ex.Message);
        }
    }

    private async void StopButton_Click(object sender, RoutedEventArgs e)
    {
        _pollCancellation?.Cancel();
        try
        {
            await _backend.StopSendByNumbersAsync();
            AddAction("Send by numbers", "Stop requested.");
        }
        catch (Exception ex)
        {
            AddAction("Send by numbers", $"Stop failed: {ex.Message}");
        }
    }

    private void ClearActionsButton_Click(object sender, RoutedEventArgs e) => _programActions.Clear();

    private void ResetForm()
    {
        MessageTextBox.Text = "";
        PhoneNumbersTextBox.Text = PhoneNumbersPlaceholder;
        SmsMinTextBox.Text = "min  1                                      sms";
        SmsMaxTextBox.Text = "max  40                                      sms";
        DelayMinTextBox.Text = "min  1";
        DelayMaxTextBox.Text = "max  10";
        FloodWaitTextBox.Text = "500                                      sec";
        SelectedAccountsTextBox.Text = "0";
        UpdatePreview();
        UpdatePhoneNumbersHeader();
    }

    private async Task LoadAccountsAsync()
    {
        try
        {
            var accounts = await _backend.GetAccountsAsync();
            _senderPhones.Clear();
            _senderPhones.AddRange(accounts.Select(account => account.Phone).Where(phone => !string.IsNullOrWhiteSpace(phone)));
            SelectedAccountsTextBox.Text = _senderPhones.Count.ToString(CultureInfo.InvariantCulture);
        }
        catch (Exception ex)
        {
            SelectedAccountsTextBox.Text = "0";
            AddAction("Accounts", $"Could not load accounts: {ex.Message}");
        }
    }

    private async Task PollStatusAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            var status = await _backend.GetSendByNumbersStatusAsync(ct);
            ApplyStatus(status);
            if (status.Finished || (!status.Running && status.JobId is null))
                break;
            await Task.Delay(1000, ct);
        }
    }

    private void ApplyStatus(SendByNumbersStatusDto status)
    {
        _programActions.Clear();
        foreach (var result in status.Results)
        {
            var account = string.IsNullOrWhiteSpace(result.SenderPhone)
                ? result.RecipientPhone
                : result.SenderPhone;
            _programActions.Add(new ProgramActionRow(
                DateTime.Now.ToString("HH:mm:ss"),
                account,
                $"{result.State}: {result.RecipientPhone} - {result.Message}"));
        }

        if (status.Finished)
        {
            AddAction(
                "Send by numbers",
                status.Error is null
                    ? $"Finished: sent {status.Sent}, failed {status.Failed}."
                    : $"Finished with error: {status.Error}");
        }
    }

    private void UpdatePreview()
    {
        if (PreviewTextBlock is null)
            return;

        PreviewTextBlock.Text = string.IsNullOrWhiteSpace(MessageTextBox.Text)
            ? "Message preview will appear here."
            : StripMarkup(MessageTextBox.Text);
    }

    private void UpdatePhoneNumbersHeader()
    {
        if (PhoneNumbersHeaderText is null)
            return;

        PhoneNumbersHeaderText.Text = $"PHONE NUMBERS : {ParsePhoneNumbers(PhoneNumbersTextBox.Text).Count}";
    }

    private void WrapSelection(string prefix, string suffix, string placeholderText)
    {
        var box = MessageTextBox;
        var selectionLength = box.SelectionLength;
        var start = box.SelectionStart;
        var inner = selectionLength > 0 ? box.SelectedText : placeholderText;

        box.Text = box.Text[..start] + prefix + inner + suffix + box.Text[(start + selectionLength)..];
        box.Focus();
        box.SelectionStart = start + prefix.Length;
        box.SelectionLength = inner.Length;
        UpdatePreview();
    }

    private void InsertAtCaret(string text)
    {
        var box = MessageTextBox;
        var start = box.SelectionStart;
        box.Text = box.Text[..start] + text + box.Text[(start + box.SelectionLength)..];
        box.Focus();
        box.SelectionStart = start + text.Length;
        UpdatePreview();
    }

    private void AddAction(string account, string message)
    {
        _programActions.Insert(0, new ProgramActionRow(
            DateTime.Now.ToString("HH:mm:ss"),
            account,
            message));
    }

    private static List<string> ParsePhoneNumbers(string raw)
    {
        if (string.IsNullOrWhiteSpace(raw)
            || raw.StartsWith("List of phone numbers", StringComparison.OrdinalIgnoreCase))
        {
            return [];
        }

        var phones = new List<string>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var line in raw.Split(["\r\n", "\n", ",", ";"], StringSplitOptions.RemoveEmptyEntries))
        {
            var digits = Regex.Replace(line, "[^0-9]", "");
            if (digits.Length is >= 7 and <= 16 && seen.Add(digits))
                phones.Add("+" + digits);
        }

        return phones;
    }

    private static int ParsePositiveInt(string? raw, int fallback)
    {
        var digits = Regex.Match(raw ?? "", @"\d+");
        if (digits.Success && int.TryParse(digits.Value, out var value) && value > 0)
            return value;
        return fallback;
    }

    private static double ParseNonNegativeDouble(string? raw, double fallback)
    {
        var match = Regex.Match(raw ?? "", @"\d+(\.\d+)?");
        if (match.Success && double.TryParse(match.Value, NumberStyles.Float, CultureInfo.InvariantCulture, out var value) && value >= 0)
            return value;
        return fallback;
    }

    private static string StripMarkup(string value)
    {
        var text = value
            .Replace("<b>", "", StringComparison.OrdinalIgnoreCase)
            .Replace("</b>", "", StringComparison.OrdinalIgnoreCase)
            .Replace("<i>", "", StringComparison.OrdinalIgnoreCase)
            .Replace("</i>", "", StringComparison.OrdinalIgnoreCase)
            .Replace("<code>", "", StringComparison.OrdinalIgnoreCase)
            .Replace("</code>", "", StringComparison.OrdinalIgnoreCase);
        return Regex.Replace(text, "<a\\s+href=\"[^\"]*\">(.*?)</a>", "$1", RegexOptions.IgnoreCase);
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
