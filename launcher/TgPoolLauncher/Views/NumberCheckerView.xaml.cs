using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.CompilerServices;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Microsoft.Win32;
using TgPoolLauncher.Models;
using TgPoolLauncher.Services;

namespace TgPoolLauncher.Views;

public partial class NumberCheckerView : UserControl
{
    private const string PhoneNumbersPlaceholder =
        "List of phone numbers, each one from a new line, in any format:\n" +
        "1(222) 333 4455\n" +
        "1 222 333 4455\n" +
        "1-222-333-4455\n" +
        "12223334455\n\n" +
        "The program removes extra spaces, brackets, and hyphens. New phone numbers are added to number_checker.xlsx and existing rows are updated.\n\n" +
        "If work was interrupted, enable Use existing results and choose number_checker.xlsx.";

    private readonly BackendClient _backend;
    private readonly ObservableCollection<SelectableAccount> _accounts = [];
    private readonly ObservableCollection<ProgramActionRow> _programActions = [];
    private CancellationTokenSource? _pollCancellation;
    private string? _lastExportPath;

    private bool _useBaseData;
    private bool _requestProfileData;
    private bool _determineGender;
    private bool _streamsControl;

    public NumberCheckerView(BackendClient backend)
    {
        _backend = backend;
        InitializeComponent();

        AccountsListBox.ItemsSource = _accounts;
        ProgramActionsList.ItemsSource = _programActions;

        ApplyVisualState();
        UpdatePhoneNumbersHeader();
        ShowReadyState();
        Loaded += async (_, _) => await RestoreJobStatusAsync();
    }

    private void UseBaseDataOnButton_Click(object sender, RoutedEventArgs e)
    {
        _useBaseData = true;
        ApplyVisualState();
    }

    private void UseBaseDataOffButton_Click(object sender, RoutedEventArgs e)
    {
        _useBaseData = false;
        ApplyVisualState();
    }

    private void ProfileDataOnButton_Click(object sender, RoutedEventArgs e)
    {
        _requestProfileData = true;
        ApplyVisualState();
    }

    private void ProfileDataOffButton_Click(object sender, RoutedEventArgs e)
    {
        _requestProfileData = false;
        ApplyVisualState();
    }

    private void GenderOnButton_Click(object sender, RoutedEventArgs e)
    {
        _determineGender = true;
        ApplyVisualState();
    }

    private void GenderOffButton_Click(object sender, RoutedEventArgs e)
    {
        _determineGender = false;
        ApplyVisualState();
    }

    private void StreamsOnButton_Click(object sender, RoutedEventArgs e)
    {
        _streamsControl = true;
        ApplyVisualState();
    }

    private void StreamsOffButton_Click(object sender, RoutedEventArgs e)
    {
        _streamsControl = false;
        ApplyVisualState();
    }

    private void ApplyVisualState()
    {
        DatabasePanel.Visibility = _useBaseData ? Visibility.Visible : Visibility.Collapsed;
        PhoneInputPanel.Visibility = _useBaseData ? Visibility.Collapsed : Visibility.Visible;
        StreamsPanel.Visibility = _streamsControl ? Visibility.Visible : Visibility.Collapsed;

        SetSegmentState(
            UseBaseDataOnButton, UseBaseDataOffButton,
            UseBaseDataOnIcon, UseBaseDataOffIcon,
            _useBaseData);
        SetSegmentState(
            ProfileDataOnButton, ProfileDataOffButton,
            ProfileDataOnIcon, ProfileDataOffIcon,
            _requestProfileData);
        SetSegmentState(
            GenderOnButton, GenderOffButton,
            GenderOnIcon, GenderOffIcon,
            _determineGender);
        SetSegmentState(
            StreamsOnButton, StreamsOffButton,
            StreamsOnIcon, StreamsOffIcon,
            _streamsControl);
    }

    private void SetSegmentState(
        Button onButton,
        Button offButton,
        Control onIcon,
        Control offIcon,
        bool isOn)
    {
        var neutral = (Brush)FindResource("SurfaceHoverBrush");
        var selected = (Brush)FindResource("AccentBrush");
        var selectedForeground = (Brush)FindResource("AppBackgroundBrush");
        var neutralForeground = (Brush)FindResource("TextMutedBrush");

        onButton.Background = isOn ? selected : neutral;
        offButton.Background = isOn ? neutral : selected;
        onIcon.Foreground = isOn ? selectedForeground : neutralForeground;
        offIcon.Foreground = isOn ? neutralForeground : selectedForeground;
    }

    private void BrowseDatabaseButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Select number_checker.xlsx",
            Filter = "Number checker workbook (number_checker.xlsx)|number_checker.xlsx|Excel workbooks (*.xlsx)|*.xlsx",
            CheckFileExists = true,
            Multiselect = false,
        };

        if (dialog.ShowDialog() == true)
            DatabasePathTextBox.Text = dialog.FileName;
    }

    private async void SelectAccountsButton_Click(object sender, RoutedEventArgs e)
    {
        AccountsOverlay.Visibility = Visibility.Visible;
        await LoadAccountsAsync();
    }

    private async Task LoadAccountsAsync()
    {
        AccountsStatusText.Text = "Loading accounts…";
        try
        {
            var previouslySelected = _accounts
                .Where(account => account.IsSelected)
                .Select(account => account.Phone)
                .ToHashSet(StringComparer.OrdinalIgnoreCase);
            var accounts = await _backend.GetAccountsAsync();

            _accounts.Clear();
            foreach (var account in accounts
                         .Where(IsUsableAccount)
                         .OrderBy(account => account.Phone))
            {
                _accounts.Add(new SelectableAccount(
                    account.Phone,
                    BuildAccountDetail(account),
                    previouslySelected.Contains(account.Phone)));
            }

            AccountsStatusText.Text = _accounts.Count == 0
                ? "No active accounts are available."
                : $"{_accounts.Count} active account(s) available";
        }
        catch (Exception ex)
        {
            AccountsStatusText.Text = $"Could not load accounts: {CleanError(ex.Message)}";
        }
    }

    private void CloseAccountsButton_Click(object sender, RoutedEventArgs e) =>
        AccountsOverlay.Visibility = Visibility.Collapsed;

    private void ApplyAccountsButton_Click(object sender, RoutedEventArgs e)
    {
        SelectedAccountsTextBox.Text =
            _accounts.Count(account => account.IsSelected).ToString();
        AccountsOverlay.Visibility = Visibility.Collapsed;
    }

    private void PhoneNumbersTextBox_TextChanged(object sender, TextChangedEventArgs e) =>
        UpdatePhoneNumbersHeader();

    private void UpdatePhoneNumbersHeader()
    {
        if (PhoneNumbersHeaderText is null || PhoneNumbersTextBox is null)
            return;

        PhoneNumbersHeaderText.Text =
            $"PHONE NUMBERS : {ParsePhoneNumbers(PhoneNumbersTextBox.Text).Count}";
    }

    private void ClearPhoneNumbersButton_Click(object sender, RoutedEventArgs e)
    {
        PhoneNumbersTextBox.Text = "";
        PhoneNumbersTextBox.Focus();
    }

    private void ResetButton_Click(object sender, RoutedEventArgs e)
    {
        if (StopButton.IsEnabled)
        {
            AddAction("Number checker", "Stop the active checker job before resetting.");
            return;
        }

        _useBaseData = false;
        _requestProfileData = false;
        _determineGender = false;
        _streamsControl = false;

        DatabasePathTextBox.Text = "Path to number_checker.xlsx";
        PhoneNumbersTextBox.Text = PhoneNumbersPlaceholder;
        DelayMinTextBox.Text = "min  5 sec";
        DelayMaxTextBox.Text = "max  10 sec";
        FloodWaitTextBox.Text = "500 sec";
        RequestsPerAccountTextBox.Text = "8 req";
        StreamsCountTextBox.Text = "4 streams";
        StreamsDelayTextBox.Text = "30–45 sec";
        _accounts.Clear();
        SelectedAccountsTextBox.Text = "0";
        _programActions.Clear();
        _lastExportPath = null;
        ResultsSummaryText.Text = "No results yet";
        SetRunningState(false);
        ApplyVisualState();
        UpdatePhoneNumbersHeader();
        ShowReadyState();
    }

    private async void StartButton_Click(object sender, RoutedEventArgs e)
    {
        var selectedAccounts = _accounts
            .Where(account => account.IsSelected)
            .Select(account => account.Phone)
            .ToList();
        var phoneNumbers = ParsePhoneNumbers(PhoneNumbersTextBox.Text);
        var hasDatabase = _useBaseData
                          && !string.IsNullOrWhiteSpace(DatabasePathTextBox.Text)
                          && DatabasePathTextBox.Text != "Path to number_checker.xlsx";

        if (selectedAccounts.Count == 0)
        {
            AddAction("Number checker", "Select at least one active account before starting.");
            return;
        }

        if (!hasDatabase && phoneNumbers.Count == 0)
        {
            AddAction(
                "Number checker",
                _useBaseData
                    ? "Choose number_checker.xlsx from a previous checker run."
                    : "Enter at least one phone number.");
            return;
        }

        var streamDelay = ParseRange(StreamsDelayTextBox.Text, 30, 45);
        _pollCancellation?.Cancel();
        _pollCancellation?.Dispose();
        _pollCancellation = new CancellationTokenSource();
        var ct = _pollCancellation.Token;

        try
        {
            var response = await _backend.StartNumberCheckerAsync(
                new NumberCheckerStartRequest
                {
                    PhoneNumbers = phoneNumbers,
                    DatabasePath = hasDatabase ? DatabasePathTextBox.Text : null,
                    SenderPhones = selectedAccounts,
                    RequestProfileData = _requestProfileData,
                    GenderDetection = _determineGender,
                    DelayMinSec = ParseNonNegativeDouble(DelayMinTextBox.Text, 5),
                    DelayMaxSec = ParseNonNegativeDouble(DelayMaxTextBox.Text, 10),
                    MaxFloodWaitSec = ParseNonNegativeDouble(FloodWaitTextBox.Text, 500),
                    RequestsPerAccount = ParsePositiveInt(RequestsPerAccountTextBox.Text, 8),
                    Streams = _streamsControl
                        ? ParsePositiveInt(StreamsCountTextBox.Text, 4)
                        : 1,
                    StreamDelayMinSec = _streamsControl ? streamDelay.Min : 0,
                    StreamDelayMaxSec = _streamsControl ? streamDelay.Max : 0,
                    RemoveImportedContacts = true,
                    ResultsDir = AppPaths.Exports,
                },
                ct);

            AddAction("Number checker", $"Started job {response.JobId}.");
            SetRunningState(true);
            await PollStatusAsync(ct);
        }
        catch (OperationCanceledException)
        {
        }
        catch (Exception ex)
        {
            AddAction("Number checker", CleanError(ex.Message));
            SetRunningState(false);
        }
    }

    private async void StopButton_Click(object sender, RoutedEventArgs e)
    {
        _pollCancellation?.Cancel();
        try
        {
            await _backend.StopNumberCheckerAsync();
            var status = await _backend.GetNumberCheckerStatusAsync();
            ApplyStatus(status);
            AddAction("Number checker", "Stopped. Unfinished numbers remain in number_checker.xlsx.");
        }
        catch (Exception ex)
        {
            AddAction("Number checker", $"Stop failed: {CleanError(ex.Message)}");
        }
        finally
        {
            SetRunningState(false);
        }
    }

    private void ClearActionsButton_Click(object sender, RoutedEventArgs e)
    {
        if (StopButton.IsEnabled)
        {
            AddAction("Number checker", "Stop the active checker job before clearing results.");
            return;
        }
        _programActions.Clear();
        ResultsSummaryText.Text = "No results yet";
    }

    private void SetRunningState(bool isRunning)
    {
        StartButton.IsEnabled = !isRunning;
        StopButton.IsEnabled = isRunning;
    }

    private void OpenResultsButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            Directory.CreateDirectory(AppPaths.Exports);
            var target = !string.IsNullOrWhiteSpace(_lastExportPath)
                         && File.Exists(_lastExportPath)
                ? Path.GetDirectoryName(_lastExportPath)!
                : AppPaths.Exports;
            Process.Start(new ProcessStartInfo(target) { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            AddAction("Results", $"Could not open results: {ex.Message}");
        }
    }

    private async Task PollStatusAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            var status = await _backend.GetNumberCheckerStatusAsync(ct);
            ApplyStatus(status);
            if (status.Finished || (!status.Running && status.JobId is null))
                return;
            await Task.Delay(1000, ct);
        }
    }

    private void ApplyStatus(NumberCheckerStatusDto status)
    {
        SetRunningState(status.Running);
        _lastExportPath = status.ExportPath;
        if (!string.IsNullOrWhiteSpace(status.DatabasePath))
            DatabasePathTextBox.Text = status.DatabasePath;

        ResultsSummaryText.Text = status.JobId is null
            ? "No results yet"
            : status.Running
                ? $"Checking {status.Total} number(s)  |  Found {status.Found}  |  "
                  + $"Not found {status.NotFound}  |  Pending {status.Pending}"
                : $"Completed {status.Total} number(s)  |  Found {status.Found}  |  "
                  + $"Not found {status.NotFound}  |  Failed {status.Failed}  |  "
                  + $"Pending {status.Pending}";

        _programActions.Clear();
        foreach (var result in status.Results.AsEnumerable().Reverse())
        {
            _programActions.Add(new ProgramActionRow(
                DateTime.Now.ToString("HH:mm:ss"),
                string.IsNullOrWhiteSpace(result.AccountPhone)
                    ? "Number checker"
                    : result.AccountPhone,
                $"{result.State}: {result.Phone} - {result.Message}"));
        }

        if (!string.IsNullOrWhiteSpace(status.Error))
        {
            _programActions.Insert(
                0,
                new ProgramActionRow(
                    DateTime.Now.ToString("HH:mm:ss"),
                    "Number checker",
                    status.Error));
        }
        else if (status.JobId is null && status.Results.Count == 0)
        {
            ShowReadyState();
        }
    }

    private async Task RestoreJobStatusAsync()
    {
        try
        {
            var status = await _backend.GetNumberCheckerStatusAsync();
            ApplyStatus(status);
            if (!status.Running)
                return;

            _pollCancellation?.Cancel();
            _pollCancellation?.Dispose();
            _pollCancellation = new CancellationTokenSource();
            await PollStatusAsync(_pollCancellation.Token);
        }
        catch (OperationCanceledException)
        {
        }
        catch (Exception ex)
        {
            AddAction("Number checker", $"Could not restore job status: {CleanError(ex.Message)}");
            SetRunningState(false);
        }
    }

    private void AddAction(string account, string message) =>
        _programActions.Insert(
            0,
            new ProgramActionRow(
                DateTime.Now.ToString("HH:mm:ss"),
                account,
                message));

    private void ShowReadyState()
    {
        if (_programActions.Count > 0)
            return;
        AddAction(
            "Number checker",
            "Ready. Enter phone numbers or select number_checker.xlsx, choose active accounts, then press Start.");
    }

    private static List<string> ParsePhoneNumbers(string? value)
    {
        if (string.IsNullOrWhiteSpace(value) || value == PhoneNumbersPlaceholder)
            return [];

        return value
            .Split(["\r\n", "\n"], StringSplitOptions.RemoveEmptyEntries)
            .Select(line => Regex.Replace(line, @"\D", ""))
            .Where(digits => digits.Length is >= 7 and <= 16)
            .Distinct(StringComparer.Ordinal)
            .Select(digits => $"+{digits}")
            .ToList();
    }

    private static int ParsePositiveInt(string? raw, int fallback)
    {
        var match = Regex.Match(raw ?? "", @"\d+");
        return match.Success
               && int.TryParse(match.Value, out var value)
               && value > 0
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

    private static (double Min, double Max) ParseRange(
        string? raw,
        double fallbackMin,
        double fallbackMax)
    {
        var values = Regex.Matches(raw ?? "", @"\d+(?:[.,]\d+)?")
            .Select(match =>
                double.TryParse(
                    match.Value.Replace(',', '.'),
                    NumberStyles.Float,
                    CultureInfo.InvariantCulture,
                    out var value)
                    ? value
                    : -1)
            .Where(value => value >= 0)
            .Take(2)
            .ToList();
        if (values.Count == 0)
            return (fallbackMin, fallbackMax);
        if (values.Count == 1)
            return (values[0], values[0]);
        return (Math.Min(values[0], values[1]), Math.Max(values[0], values[1]));
    }

    private static bool IsUsableAccount(AccountDto account)
    {
        var blocked = new[] { "banned", "unauthorized", "spamblock", "frozen" };
        return !string.IsNullOrWhiteSpace(account.Phone)
               && !blocked.Contains(account.Status, StringComparer.OrdinalIgnoreCase)
               && (string.IsNullOrWhiteSpace(account.Folder)
                   || account.Folder.Equals("active", StringComparison.OrdinalIgnoreCase));
    }

    private static string BuildAccountDetail(AccountDto account)
    {
        var values = new[] { account.Status, account.Country, account.Folder }
            .Where(value => !string.IsNullOrWhiteSpace(value));
        return string.Join("  |  ", values);
    }

    private static string CleanError(string value)
    {
        var detail = Regex.Match(value, "\"detail\"\\s*:\\s*\"([^\"]+)\"");
        return detail.Success ? detail.Groups[1].Value : value;
    }

    private sealed class SelectableAccount : INotifyPropertyChanged
    {
        private bool _isSelected;

        public SelectableAccount(string phone, string detail, bool isSelected)
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
