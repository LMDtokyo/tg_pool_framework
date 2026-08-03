using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Runtime.CompilerServices;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Xml.Linq;
using Microsoft.Win32;
using TgPoolLauncher.Localization;
using TgPoolLauncher.Models;
using TgPoolLauncher.Services;

namespace TgPoolLauncher.Views;

public partial class InviteByNumberView : UserControl
{
    // Sample ID baked into the placeholder text in every language (see
    // InviteByNumberStrings.ReceiverIdsPlaceholder) -- used to detect an
    // untouched box regardless of which language it was populated in.
    private const string PlaceholderSentinel = "8535286786";

    private static string ReceiverIdsPlaceholder =>
        LocalizationService.Instance["InviteByNumber.ReceiverIdsPlaceholder"];

    private static string DatabasePathPlaceholder =>
        LocalizationService.Instance["InviteByNumber.DatabasePathPlaceholder"];

    private static readonly HashSet<string> PhoneHeaderNames = new(StringComparer.OrdinalIgnoreCase)
    {
        "PhoneNumber",
        "Phone",
        "Телефон",
    };

    private static readonly HashSet<string> UsernameHeaderNames = new(StringComparer.OrdinalIgnoreCase)
    {
        "Telegram_ID",
        "Username",
        "UserName",
        "Юзернейм",
    };

    private readonly BackendClient _backend;
    private readonly ObservableCollection<ProgramActionRow> _programActions = new();
    private readonly List<ReceiverRow> _baseReceivers = new();
    private readonly List<string> _senderAccounts = new();
    private readonly Dictionary<string, string> _senderLabelToPhone = new(StringComparer.OrdinalIgnoreCase);
    private CancellationTokenSource? _pollCancellation;
    private bool _useBaseData = true;

    public InviteByNumberView(BackendClient backend)
    {
        _backend = backend;
        InitializeComponent();
        ProgramActionsGrid.ItemsSource = _programActions;
        PhoneNumbersTextBox.Text = ReceiverIdsPlaceholder;
        BaseDataPathTextBox.Text = DatabasePathPlaceholder;
        Loaded += async (_, _) => await LoadAccountGroupsAsync();
    }

    private void UseBaseDataOkButton_Click(object sender, RoutedEventArgs e)
    {
        _useBaseData = true;
        BaseDataPanel.Visibility = Visibility.Visible;
        UseBaseDataOkButton.Background = (System.Windows.Media.Brush)new System.Windows.Media.BrushConverter().ConvertFrom("#1D8A78")!;
        UseBaseDataNoButton.Background = (System.Windows.Media.Brush)FindResource("SurfaceHoverBrush");
        UpdateReceiverIdsHeader();
    }

    private void UseBaseDataNoButton_Click(object sender, RoutedEventArgs e)
    {
        _useBaseData = false;
        BaseDataPanel.Visibility = Visibility.Collapsed;
        BaseDataPathTextBox.Text = DatabasePathPlaceholder;
        UseBaseDataOkButton.Background = (System.Windows.Media.Brush)FindResource("SurfaceHoverBrush");
        UseBaseDataNoButton.Background = (System.Windows.Media.Brush)new System.Windows.Media.BrushConverter().ConvertFrom("#6D0616")!;
        UpdateReceiverIdsHeader();
    }

    private void BrowseBaseDataButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = LocalizationService.Instance["InviteByNumber.SelectDatabaseDialogTitle"],
            Filter = LocalizationService.Instance["InviteByNumber.ExcelWorkbookFilter"],
            CheckFileExists = true,
            Multiselect = false,
        };

        if (dialog.ShowDialog() != true)
            return;

        BaseDataPathTextBox.Text = dialog.FileName;
        var rows = ReadReceiversFromXlsx(dialog.FileName);
        _baseReceivers.Clear();
        if (rows.Count == 0)
        {
            _programActions.Insert(0, new ProgramActionRow(
                DateTime.Now.ToString("HH:mm:ss"),
                account: LocalizationService.Instance["InviteByNumber.BaseDataJobLabel"],
                recipientId: "",
                state: "ready",
                message: string.Format(
                    LocalizationService.Instance["InviteByNumber.NoIdsFoundFormat"],
                    Path.GetFileName(dialog.FileName))));
            UpdateReceiverIdsHeader();
            return;
        }

        foreach (var row in rows)
        {
            _baseReceivers.Add(row);
            _programActions.Add(new ProgramActionRow(
                DateTime.Now.ToString("HH:mm:ss"),
                account: DisplayAccount(row),
                recipientId: row.ReceiverId,
                state: "ready",
                message: BuildReadyMessage(row, Path.GetFileName(dialog.FileName))));
        }
        UpdateReceiverIdsHeader();
    }

    private void PhoneNumbersTextBox_TextChanged(object sender, TextChangedEventArgs e) =>
        UpdateReceiverIdsHeader();

    private void ClearPhoneNumbersButton_Click(object sender, RoutedEventArgs e)
    {
        PhoneNumbersTextBox.Text = ReceiverIdsPlaceholder;
        UpdateReceiverIdsHeader();
    }

    private async void RunInviteActionsButton_Click(object sender, RoutedEventArgs e)
    {
        var recipients = CollectRecipients();
        var senderLinks = ParseSenderInviteLinks(GroupsTextBox.Text, _senderAccounts);
        if (recipients.Count == 0)
        {
            AddStatusRow(
                LocalizationService.Instance["InviteByNumber.JobLabel"],
                "ready",
                _useBaseData
                    ? LocalizationService.Instance["InviteByNumber.NoBaseDataMessage"]
                    : LocalizationService.Instance["InviteByNumber.NoManualIdsMessage"]);
            return;
        }

        if (senderLinks.Count == 0)
        {
            AddStatusRow(
                LocalizationService.Instance["InviteByNumber.JobLabel"],
                "ready",
                LocalizationService.Instance["InviteByNumber.NoInviteLinksMessage"]);
            return;
        }

        var senderPhones = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var apiLinks = new List<InviteSenderLinkRequest>();
        foreach (var link in senderLinks)
        {
            var senderPhone = ResolveSenderPhone(link.SenderAccount);
            if (senderPhone is null)
            {
                AddStatusRow(link.SenderAccount, "failed", LocalizationService.Instance["InviteByNumber.SenderMappingFailedMessage"]);
                return;
            }
            senderPhones.Add(senderPhone);
            apiLinks.Add(new InviteSenderLinkRequest
            {
                SenderPhone = senderPhone,
                InviteLink = link.InviteLink,
            });
        }

        var apiRecipients = recipients.Select(row => new InviteRecipientRequest
        {
            Id = row.ReceiverId,
            Username = string.IsNullOrWhiteSpace(row.Username) ? null : row.Username,
            Phone = IsSenderPhone(row.PhoneNumber, senderPhones) ? null : NullIfEmpty(row.PhoneNumber),
        }).ToList();

        _pollCancellation?.Cancel();
        _pollCancellation = new CancellationTokenSource();
        var ct = _pollCancellation.Token;

        _programActions.Clear();
        foreach (var row in recipients)
        {
            _programActions.Add(new ProgramActionRow(
                DateTime.Now.ToString("HH:mm:ss"),
                account: DisplayAccount(row, senderPhones),
                recipientId: row.ReceiverId,
                state: "pending",
                message: string.Format(
                    LocalizationService.Instance["InviteByNumber.QueuedForFormat"],
                    DisplayAccount(row, senderPhones),
                    row.ReceiverId)));
        }

        try
        {
            var response = await _backend.StartInviteByNumberAsync(new InviteByNumberStartRequest
            {
                Recipients = apiRecipients,
                SenderLinks = apiLinks,
                MaxPerAccount = ParsePositiveInt(MaxPerAccountTextBox.Text, 40),
                DelayMinSec = ParseNonNegativeDouble(DelayMinTextBox.Text, 1),
                DelayMaxSec = ParseNonNegativeDouble(DelayMaxTextBox.Text, 10),
                MaxFloodWaitSec = ParseNonNegativeDouble(MaxFloodWaitTextBox.Text, 500),
                RequireProxy = RequireProxyToggle.IsChecked == true,
            }, ct);

            AddStatusRow(
                LocalizationService.Instance["InviteByNumber.JobLabel"],
                "running",
                string.Format(LocalizationService.Instance["InviteByNumber.StartedJobFormat"], response.JobId));
            await PollInviteStatusAsync(ct);
        }
        catch (OperationCanceledException)
        {
            AddStatusRow(
                LocalizationService.Instance["InviteByNumber.JobLabel"],
                "ready",
                LocalizationService.Instance["InviteByNumber.RequestsStoppedMessage"]);
        }
        catch (Exception ex)
        {
            AddStatusRow(LocalizationService.Instance["InviteByNumber.JobLabel"], "failed", ex.Message);
            foreach (var row in _programActions.Where(r => r.State is "pending" or "sending" or "waiting"))
            {
                row.State = "failed";
                row.Message = LocalizationService.Instance["InviteByNumber.JobFailedToStartMessage"];
            }
        }
    }

    private async void StopInviteActionsButton_Click(object sender, RoutedEventArgs e)
    {
        _pollCancellation?.Cancel();
        try
        {
            await _backend.StopInviteByNumberAsync();
            AddStatusRow(
                LocalizationService.Instance["InviteByNumber.JobLabel"],
                "ready",
                LocalizationService.Instance["InviteByNumber.StopRequestedMessage"]);
        }
        catch (Exception ex)
        {
            AddStatusRow(
                LocalizationService.Instance["InviteByNumber.JobLabel"],
                "failed",
                string.Format(LocalizationService.Instance["InviteByNumber.StopFailedFormat"], ex.Message));
        }
    }

    private void ClearProgramActionsButton_Click(object sender, RoutedEventArgs e)
    {
        _pollCancellation?.Cancel();
        _pollCancellation?.Dispose();
        _pollCancellation = null;
        _programActions.Clear();
        _baseReceivers.Clear();
        BaseDataPathTextBox.Text = DatabasePathPlaceholder;
        UpdateReceiverIdsHeader();
    }

    private async void RefreshGroupsButton_Click(object sender, RoutedEventArgs e)
    {
        await LoadAccountGroupsAsync();
    }

    private async Task PollInviteStatusAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            var status = await _backend.GetInviteByNumberStatusAsync(ct);
            ApplyStatus(status);
            if (status.Finished || (!status.Running && status.JobId is null))
                break;
            await Task.Delay(1000, ct);
        }
    }

    private void ApplyStatus(InviteByNumberStatusDto status)
    {
        var byId = status.Results
            .GroupBy(r => r.RecipientId, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(g => g.Key, g => g.Last(), StringComparer.OrdinalIgnoreCase);

        foreach (var row in _programActions.Where(r => !string.IsNullOrEmpty(r.RecipientId)))
        {
            if (!byId.TryGetValue(row.RecipientId, out var result))
                continue;
            row.Time = DateTime.Now.ToString("HH:mm:ss");
            row.State = result.State;
            row.Message = string.IsNullOrWhiteSpace(result.Message)
                ? string.Format(LocalizationService.Instance["InviteByNumber.ViaSenderFormat"], result.State, result.SenderPhone)
                : result.Message;
        }

        if (status.Finished)
        {
            var summary = status.Error is null
                ? string.Format(LocalizationService.Instance["InviteByNumber.FinishedSummaryFormat"], status.Sent, status.Failed)
                : string.Format(LocalizationService.Instance["InviteByNumber.FinishedErrorFormat"], status.Error);
            AddStatusRow(LocalizationService.Instance["InviteByNumber.JobLabel"], status.Error is null ? "sent" : "failed", summary);
        }
    }

    private async Task LoadAccountGroupsAsync()
    {
        try
        {
            var accounts = await _backend.GetAccountsAsync();
            _senderAccounts.Clear();
            _senderLabelToPhone.Clear();
            var lines = new List<string>();
            foreach (var account in accounts)
            {
                if (lines.Count > 0)
                    lines.Add("");

                _senderAccounts.Add(account.Phone);
                _senderLabelToPhone[NormalizeAccountKey(account.Phone)] = account.Phone;
                if (!string.IsNullOrWhiteSpace(account.TelegramId)
                    && !string.Equals(account.TelegramId, account.Phone, StringComparison.OrdinalIgnoreCase))
                {
                    _senderAccounts.Add(account.TelegramId);
                    _senderLabelToPhone[NormalizeAccountKey(account.TelegramId)] = account.Phone;
                }

                lines.Add(account.Phone);
                lines.Add("# paste https://t.me/+... invite link(s) below");
            }

            GroupsTextBox.Text = lines.Count == 0
                ? "Number\r\n# paste https://t.me/+... invite link(s) below"
                : string.Join(Environment.NewLine, lines);
        }
        catch (Exception ex)
        {
            GroupsTextBox.Text = $"Number{Environment.NewLine}Error: {ex.Message}";
        }
    }

    private List<ReceiverRow> CollectRecipients()
    {
        var rows = new List<ReceiverRow>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        if (_useBaseData)
        {
            foreach (var row in _baseReceivers)
            {
                if (seen.Add(row.ReceiverId))
                    rows.Add(row);
            }
        }

        foreach (var id in ParseReceiverIdsText(PhoneNumbersTextBox.Text))
        {
            if (seen.Add(id))
                rows.Add(new ReceiverRow(id, "", id.StartsWith('@') ? id : ""));
        }

        return rows;
    }

    private void UpdateReceiverIdsHeader()
    {
        if (PhoneNumbersHeaderText is null)
            return;
        PhoneNumbersHeaderText.Text = string.Format(
            LocalizationService.Instance["InviteByNumber.ReceiverIdsHeaderFormat"],
            CollectRecipients().Count);
    }

    private static string DisplayAccount(ReceiverRow row, ISet<string>? senderPhones = null)
    {
        if (!string.IsNullOrWhiteSpace(row.PhoneNumber) && !IsSenderPhone(row.PhoneNumber, senderPhones))
            return row.PhoneNumber;
        if (!string.IsNullOrWhiteSpace(row.Username))
            return row.Username;
        return row.ReceiverId;
    }

    private static string BuildReadyMessage(ReceiverRow row, string fileName)
    {
        var parts = new List<string> { string.Format(LocalizationService.Instance["InviteByNumber.IdLabelFormat"], row.ReceiverId) };
        if (!string.IsNullOrWhiteSpace(row.Username))
            parts.Add(row.Username);
        if (!string.IsNullOrWhiteSpace(row.PhoneNumber))
            parts.Add(row.PhoneNumber);
        return string.Format(
            LocalizationService.Instance["InviteByNumber.AddedFromFileFormat"],
            string.Join(" / ", parts),
            fileName);
    }

    private static bool IsSenderPhone(string? phone, ISet<string>? senderPhones)
    {
        if (string.IsNullOrWhiteSpace(phone) || senderPhones is null || senderPhones.Count == 0)
            return false;
        return senderPhones.Contains(phone);
    }

    private static string? NullIfEmpty(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value;

    private string? ResolveSenderPhone(string senderAccount)
    {
        var key = NormalizeAccountKey(senderAccount);
        if (_senderLabelToPhone.TryGetValue(key, out var phone))
            return phone;

        var digits = Regex.Replace(senderAccount, "[^0-9]", "");
        return digits.Length is >= 7 and <= 16 ? "+" + digits : null;
    }

    private void AddStatusRow(string account, string state, string message)
    {
        _programActions.Insert(0, new ProgramActionRow(
            DateTime.Now.ToString("HH:mm:ss"),
            account: account,
            recipientId: "",
            state: state,
            message: message));
    }

    private static List<string> ParseReceiverIdsText(string raw)
    {
        if (string.IsNullOrWhiteSpace(raw)
            || raw.Contains(PlaceholderSentinel, StringComparison.Ordinal))
        {
            return [];
        }

        var ids = new List<string>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var line in raw.Split(["\r\n", "\n", ","], StringSplitOptions.RemoveEmptyEntries))
        {
            var id = NormalizeReceiverId(line);
            if (id is not null && seen.Add(id))
                ids.Add(id);
        }
        return ids;
    }

    private static List<ReceiverRow> ReadReceiversFromXlsx(string path)
    {
        var receivers = new List<ReceiverRow>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        using var archive = ZipFile.OpenRead(path);
        var sharedStrings = ReadSharedStrings(archive);
        foreach (var worksheet in archive.Entries.Where(e => e.FullName.StartsWith("xl/worksheets/", StringComparison.OrdinalIgnoreCase)
                                                             && e.FullName.EndsWith(".xml", StringComparison.OrdinalIgnoreCase)))
        {
            using var stream = worksheet.Open();
            var document = XDocument.Load(stream);
            var rows = document.Descendants()
                .Where(e => e.Name.LocalName == "row")
                .Select(row => row.Elements()
                    .Where(e => e.Name.LocalName == "c")
                    .Select(cell => new CellValue(
                        GetColumnName(cell.Attribute("r")?.Value),
                        ReadCellText(cell, sharedStrings)))
                    .Where(cell => !string.IsNullOrWhiteSpace(cell.Column))
                    .ToList())
                .Where(row => row.Count > 0)
                .ToList();

            var headerRow = rows.FirstOrDefault(row =>
                row.Any(cell => string.Equals(cell.Text.Trim(), "ID", StringComparison.OrdinalIgnoreCase)));
            if (headerRow is null)
                continue;

            var idColumn = headerRow
                .First(cell => string.Equals(cell.Text.Trim(), "ID", StringComparison.OrdinalIgnoreCase))
                .Column;
            var phoneColumn = headerRow
                .FirstOrDefault(cell => PhoneHeaderNames.Contains(cell.Text.Trim()))
                ?.Column;
            var usernameColumn = headerRow
                .FirstOrDefault(cell => UsernameHeaderNames.Contains(cell.Text.Trim()))
                ?.Column;

            foreach (var row in rows)
            {
                if (ReferenceEquals(row, headerRow))
                    continue;

                var idText = row.FirstOrDefault(cell => cell.Column == idColumn)?.Text ?? "";
                var receiverId = NormalizeReceiverId(idText);
                if (receiverId is null || !seen.Add(receiverId))
                    continue;

                string? phoneNumber = null;
                if (phoneColumn is not null)
                {
                    var phoneText = row.FirstOrDefault(cell => cell.Column == phoneColumn)?.Text ?? "";
                    phoneNumber = NormalizePhoneNumber(phoneText);
                }

                string? username = null;
                if (usernameColumn is not null)
                {
                    var usernameText = row.FirstOrDefault(cell => cell.Column == usernameColumn)?.Text ?? "";
                    username = NormalizeUsername(usernameText);
                }

                receivers.Add(new ReceiverRow(receiverId, phoneNumber ?? "", username ?? ""));
            }
        }

        return receivers;
    }

    private static string? NormalizeUsername(string value)
    {
        var trimmed = value.Trim();
        if (string.IsNullOrWhiteSpace(trimmed))
            return null;
        if (trimmed.StartsWith('@'))
            trimmed = trimmed[1..];
        var username = Regex.Replace(trimmed, "[^A-Za-z0-9_]", "");
        return username.Length == 0 ? null : "@" + username;
    }

    private static string? NormalizePhoneNumber(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
            return null;

        if (decimal.TryParse(value.Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out var numericValue))
            value = decimal.Truncate(numericValue).ToString(CultureInfo.InvariantCulture);

        var digits = Regex.Replace(value, "[^0-9]", "");
        if (digits.Length < 7 || digits.Length > 16)
            return null;
        return "+" + digits;
    }

    private static List<string> ReadSharedStrings(ZipArchive archive)
    {
        var entry = archive.GetEntry("xl/sharedStrings.xml");
        if (entry is null)
            return [];

        using var stream = entry.Open();
        var document = XDocument.Load(stream);
        return document.Descendants()
            .Where(e => e.Name.LocalName == "si")
            .Select(si => string.Concat(si.Descendants().Where(e => e.Name.LocalName == "t").Select(t => t.Value)))
            .ToList();
    }

    private static string ReadCellText(XElement cell, IReadOnlyList<string> sharedStrings)
    {
        var type = cell.Attribute("t")?.Value;
        if (type == "inlineStr")
            return string.Concat(cell.Descendants().Where(e => e.Name.LocalName == "t").Select(t => t.Value));

        var raw = cell.Elements().FirstOrDefault(e => e.Name.LocalName == "v")?.Value ?? "";
        if (type == "s" && int.TryParse(raw, out var sharedIndex) && sharedIndex >= 0 && sharedIndex < sharedStrings.Count)
            return sharedStrings[sharedIndex];
        return raw;
    }

    private static string GetColumnName(string? cellReference)
    {
        if (string.IsNullOrWhiteSpace(cellReference))
            return "";

        return new string(cellReference.TakeWhile(char.IsLetter).ToArray()).ToUpperInvariant();
    }

    private static string? NormalizeReceiverId(string value)
    {
        var trimmed = value.Trim();
        if (trimmed.StartsWith('@'))
        {
            var username = Regex.Replace(trimmed[1..], "[^A-Za-z0-9_]", "");
            return username.Length == 0 ? null : "@" + username;
        }

        if (decimal.TryParse(trimmed, NumberStyles.Float, CultureInfo.InvariantCulture, out var numericValue))
            trimmed = decimal.Truncate(numericValue).ToString(CultureInfo.InvariantCulture);

        var digits = Regex.Replace(trimmed, "[^0-9]", "");
        if (digits.Length < 5 || digits.Length > 18)
            return null;
        return digits;
    }

    private static List<SenderInviteLink> ParseSenderInviteLinks(string rawGroups, IReadOnlyCollection<string> senderAccounts)
    {
        var knownSenders = new HashSet<string>(
            senderAccounts.Select(NormalizeAccountKey).Where(key => key.Length > 0),
            StringComparer.OrdinalIgnoreCase);
        var result = new List<SenderInviteLink>();
        string? currentSender = null;

        foreach (var line in rawGroups
            .Split(["\r\n", "\n", ","], StringSplitOptions.RemoveEmptyEntries)
            .Select(group => group.Trim()))
        {
            if (string.Equals(line, "Number", StringComparison.OrdinalIgnoreCase)
                || line.StartsWith('#')
                || line.StartsWith("Error:", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            var accountKey = NormalizeAccountKey(line);
            if (knownSenders.Contains(accountKey))
            {
                currentSender = line;
                continue;
            }

            var inviteLink = NormalizeInviteLink(line);
            if (currentSender is not null && inviteLink is not null)
                result.Add(new SenderInviteLink(currentSender, inviteLink));
        }

        return result
            .DistinctBy(item => $"{NormalizeAccountKey(item.SenderAccount)}|{item.InviteLink}", StringComparer.OrdinalIgnoreCase)
            .ToList();
    }

    private static string? NormalizeInviteLink(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
            return null;

        var linkedValue = Regex.Match(value, @"https://t\.me/[A-Za-z0-9_+\-/]+", RegexOptions.IgnoreCase);
        if (linkedValue.Success)
            return linkedValue.Value;

        if (Uri.TryCreate(value, UriKind.Absolute, out var uri)
            && string.Equals(uri.Host, "t.me", StringComparison.OrdinalIgnoreCase)
            && !string.IsNullOrWhiteSpace(uri.AbsolutePath.Trim('/')))
        {
            return value;
        }

        return null;
    }

    private static string NormalizeAccountKey(string value) =>
        Regex.Replace(value, "[^0-9A-Za-z_+@]", "");

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

    private sealed record CellValue(string Column, string Text);
    private sealed record ReceiverRow(string ReceiverId, string PhoneNumber, string Username);
    private sealed record SenderInviteLink(string SenderAccount, string InviteLink);

    private sealed class ProgramActionRow : INotifyPropertyChanged
    {
        private string _time;
        private string _account;
        private string _message;
        private string _state;

        public ProgramActionRow(string time, string account, string recipientId, string state, string message)
        {
            _time = time;
            _account = account;
            RecipientId = recipientId;
            _state = state;
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

        public string RecipientId { get; }

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

        public string State
        {
            get => _state;
            set
            {
                if (_state == value)
                    return;
                _state = value;
                OnPropertyChanged();
            }
        }

        public event PropertyChangedEventHandler? PropertyChanged;

        private void OnPropertyChanged([CallerMemberName] string? propertyName = null) =>
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }
}
