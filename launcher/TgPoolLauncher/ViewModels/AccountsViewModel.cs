using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using TgPoolLauncher.Converters;
using TgPoolLauncher.Localization;
using TgPoolLauncher.Models;
using TgPoolLauncher.Services;

namespace TgPoolLauncher.ViewModels;

public sealed record FilterOption(string? Value, string Label);

public partial class AccountsViewModel : ObservableObject
{
    private static FilterOption AllStatuses => new(null, LocalizationService.Instance["Accounts.FilterStatusAll"]);
    private static FilterOption AllRoles => new(null, LocalizationService.Instance["Accounts.FilterRoleAll"]);
    private static FilterOption AllFolders => new(null, LocalizationService.Instance["Accounts.FilterFolderAll"]);
    private static FilterOption AllGeos => new(null, LocalizationService.Instance["Accounts.FilterGeoAll"]);

    private readonly BackendClient _backend;
    private bool _suppressSelectAllReentry;

    [ObservableProperty]
    private string searchText = "";

    [ObservableProperty]
    private bool isBusy;

    [ObservableProperty]
    private string statusMessage = "";

    [ObservableProperty]
    private bool isAllSelected;

    [ObservableProperty]
    private FilterOption selectedStatusFilter;

    [ObservableProperty]
    private FilterOption selectedRoleFilter;

    [ObservableProperty]
    private FilterOption selectedFolderFilter;

    [ObservableProperty]
    private FilterOption selectedGeoFilter;

    [ObservableProperty]
    private string defaultApiId = "";

    [ObservableProperty]
    private string defaultApiHash = "";

    [ObservableProperty]
    private string defaultCredentialsStatus = "";

    public ObservableCollection<SelectableAccountRow> Accounts { get; } = new();

    public ObservableCollection<FilterOption> StatusOptions { get; } = new();
    public ObservableCollection<FilterOption> RoleOptions { get; } = new([AllRoles]);
    public ObservableCollection<FilterOption> FolderOptions { get; } = new([AllFolders]);
    public ObservableCollection<FilterOption> GeoOptions { get; } = new([AllGeos]);

    public AccountsViewModel(BackendClient backend)
    {
        _backend = backend;
        selectedStatusFilter = AllStatuses;
        selectedRoleFilter = AllRoles;
        selectedFolderFilter = AllFolders;
        selectedGeoFilter = AllGeos;
        RebuildStatusOptions();

        // Static labels (filter placeholders, status badges) are only re-resolved when their
        // bound source object changes -- a language switch alone doesn't touch Accounts/filter
        // data, so nothing would refresh without an explicit reload here.
        LocalizationService.Instance.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == "Item[]")
                LoadCommand.Execute(null);
        };

        _ = LoadDefaultCredentialsAsync();
    }

    private async Task LoadDefaultCredentialsAsync()
    {
        try
        {
            var current = await _backend.GetDefaultCredentialsAsync();
            if (current.ApiId > 0)
            {
                DefaultApiId = current.ApiId.ToString();
                DefaultApiHash = current.ApiHash;
            }
        }
        catch (Exception)
        {
            // ignored -- the field just starts empty if the backend isn't reachable yet
        }
    }

    [RelayCommand]
    private async Task SaveDefaultCredentialsAsync()
    {
        if (!int.TryParse(DefaultApiId, out var apiId) || apiId <= 0
            || DefaultApiHash.Length != 32 || !DefaultApiHash.All(Uri.IsHexDigit))
        {
            DefaultCredentialsStatus = LocalizationService.Instance["Accounts.DefaultCredentialsInvalid"];
            return;
        }

        try
        {
            await _backend.SetDefaultCredentialsAsync(apiId, DefaultApiHash);
            DefaultCredentialsCacheFile.Save(
                AppPaths.Data, new CachedDefaultCredentials { ApiId = apiId, ApiHash = DefaultApiHash });
            DefaultCredentialsStatus = LocalizationService.Instance["Accounts.DefaultCredentialsSaved"];
        }
        catch (Exception)
        {
            DefaultCredentialsStatus = LocalizationService.Instance["Accounts.DefaultCredentialsSaveFailed"];
        }
    }

#pragma warning disable MVVMTK0034
    private void RebuildStatusOptions()
    {
        var previous = SelectedStatusFilter?.Value;
        StatusOptions.Clear();
        StatusOptions.Add(AllStatuses);
        foreach (var (value, labelKey) in StatusPresentation.AllOptions)
            StatusOptions.Add(new FilterOption(value, LocalizationService.Instance[labelKey]));

        selectedStatusFilter = StatusOptions.FirstOrDefault(o => o.Value == previous) ?? StatusOptions[0];
        OnPropertyChanged(nameof(SelectedStatusFilter));
    }
#pragma warning restore MVVMTK0034

    // FilterOption? (not FilterOption): RefreshFilterOptions() below clears+repopulates the
    // Role/Folder/Geo ItemsSource collections in place, and WPF's ComboBox transiently nulls
    // out its TwoWay-bound SelectedItem while the list is momentarily empty. That transient
    // null must not trigger a reload -- it isn't a real user filter change, and reloading
    // from inside a reload (via the very Clear() that caused it) is a reentrant call.
    partial void OnSelectedStatusFilterChanged(FilterOption value)
    {
        if (value is not null) LoadCommand.Execute(null);
    }

    partial void OnSelectedRoleFilterChanged(FilterOption value)
    {
        if (value is not null) LoadCommand.Execute(null);
    }

    partial void OnSelectedFolderFilterChanged(FilterOption value)
    {
        if (value is not null) LoadCommand.Execute(null);
    }

    partial void OnSelectedGeoFilterChanged(FilterOption value)
    {
        if (value is not null) LoadCommand.Execute(null);
    }

    partial void OnIsAllSelectedChanged(bool value)
    {
        if (_suppressSelectAllReentry)
            return;

        foreach (var row in Accounts)
            row.IsSelected = value;
    }

    [RelayCommand]
    private async Task LoadAsync()
    {
        IsBusy = true;
        StatusMessage = "";
        try
        {
            RebuildStatusOptions();

            // Best-effort: pick up any .session+.json pairs dropped into Data\Accounts
            // since startup before listing. A rescan failure must not block the list
            // from loading with whatever accounts are already known.
            try
            {
                await _backend.RescanAccountsAsync();
            }
            catch (Exception)
            {
                // ignored -- rescan is a nice-to-have, not required for the list to load
            }

            var accounts = await _backend.GetAccountsAsync(
                status: SelectedStatusFilter?.Value,
                role: SelectedRoleFilter?.Value,
                folder: SelectedFolderFilter?.Value,
                country: SelectedGeoFilter?.Value,
                text: string.IsNullOrWhiteSpace(SearchText) ? null : SearchText);

            foreach (var row in Accounts)
                row.PropertyChanged -= OnRowPropertyChanged;

            Accounts.Clear();
            foreach (var account in accounts)
            {
                var row = new SelectableAccountRow(account);
                row.PropertyChanged += OnRowPropertyChanged;
                Accounts.Add(row);
            }

            // Capture the filters the user actually has selected *before* touching the
            // ItemsSource collections below -- Clear() transiently nulls the ComboBoxes'
            // TwoWay-bound SelectedItem, which would otherwise wipe these out.
            var previousRole = SelectedRoleFilter?.Value;
            var previousFolder = SelectedFolderFilter?.Value;
            var previousGeo = SelectedGeoFilter?.Value;

            // MVVMTK0034 suppressed: assigning the backing fields directly (instead of the
            // generated properties) is intentional here -- it re-syncs the ComboBoxes without
            // re-running OnSelected*FilterChanged, which would otherwise call LoadCommand
            // again from inside the load that's still executing.
#pragma warning disable MVVMTK0034
            RefreshFilterOptions(RoleOptions, AllRoles, accounts.Select(a => a.Role), previousRole,
                v => { selectedRoleFilter = v; OnPropertyChanged(nameof(SelectedRoleFilter)); });
            RefreshFilterOptions(FolderOptions, AllFolders, accounts.Select(a => a.Folder), previousFolder,
                v => { selectedFolderFilter = v; OnPropertyChanged(nameof(SelectedFolderFilter)); });
            RefreshFilterOptions(GeoOptions, AllGeos, accounts.Select(a => a.Country), previousGeo,
                v => { selectedGeoFilter = v; OnPropertyChanged(nameof(SelectedGeoFilter)); });
#pragma warning restore MVVMTK0034

            UpdateIsAllSelected();
            StatusMessage = string.Format(LocalizationService.Instance["Accounts.StatusCountFormat"], Accounts.Count);
        }
        catch (Exception ex)
        {
            StatusMessage = string.Format(LocalizationService.Instance["Accounts.LoadErrorFormat"], ex.Message);
        }
        finally
        {
            IsBusy = false;
        }
    }

    /// <summary>
    /// Rebuilds a filter dropdown's options in place, then restores whatever the user had
    /// selected (by value, since RefreshFilterOptions always mints new FilterOption
    /// instances) -- or "Все" if that value no longer appears in the fresh data.
    /// The restore callback assigns the backing field directly and raises PropertyChanged
    /// itself rather than going through the generated property setter, so it re-syncs the
    /// ComboBox without re-triggering the On...Changed reload hook (which would recurse).
    /// </summary>
    private static void RefreshFilterOptions(
        ObservableCollection<FilterOption> options, FilterOption allOption, IEnumerable<string?> values,
        string? previousValue, Action<FilterOption> restoreSelection)
    {
        var distinct = values
            .Where(v => !string.IsNullOrWhiteSpace(v))
            .Distinct()
            .OrderBy(v => v, StringComparer.CurrentCultureIgnoreCase)
            .Select(v => new FilterOption(v, v!))
            .ToList();

        options.Clear();
        options.Add(allOption);
        foreach (var option in distinct)
            options.Add(option);

        restoreSelection(distinct.FirstOrDefault(o => o.Value == previousValue) ?? allOption);
    }

    private void OnRowPropertyChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(SelectableAccountRow.IsSelected))
            UpdateIsAllSelected();
    }

    private void UpdateIsAllSelected()
    {
        _suppressSelectAllReentry = true;
        IsAllSelected = Accounts.Count > 0 && Accounts.All(row => row.IsSelected);
        _suppressSelectAllReentry = false;
    }

    [RelayCommand]
    private async Task RecheckAsync()
    {
        IsBusy = true;
        StatusMessage = "";
        try
        {
            var result = await _backend.RecheckAsync(deep: false);
            await LoadAsync();
            StatusMessage = string.Format(LocalizationService.Instance["Accounts.RecheckResultFormat"],
                result.Checked, result.Alive, result.Banned, result.Unauthorized);
        }
        catch (Exception ex)
        {
            // A server-side response failure can happen after the checker has already
            // committed fresh states. Always re-read the list so the UI never remains
            // stuck on stale values merely because the summary response failed.
            await LoadAsync();
            StatusMessage = string.Format(LocalizationService.Instance["Accounts.RecheckErrorFormat"], ex.Message);
        }
        finally
        {
            IsBusy = false;
        }
    }
}
