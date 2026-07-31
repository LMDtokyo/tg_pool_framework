using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using TgPoolLauncher.Localization;
using TgPoolLauncher.Models;

namespace TgPoolLauncher.ViewModels;

public partial class ManualViewModel : ObservableObject
{
    private static readonly (string Key, string TitleKey, string BodyKey, string Icon)[] Definitions =
    [
        ("getting-started", "Manual.GettingStarted.Title", "Manual.GettingStarted.Body", "RocketLaunchOutline"),
        ("data-folder", "Manual.DataFolder.Title", "Manual.DataFolder.Body", "FolderOutline"),
        ("accounts", "Manual.Accounts.Title", "Manual.Accounts.Body", "AccountGroup"),
        ("fingerprints", "Manual.Fingerprints.Title", "Manual.Fingerprints.Body", "Fingerprint"),
        ("proxies", "Manual.Proxies.Title", "Manual.Proxies.Body", "ServerNetwork"),
        ("safety", "Manual.Safety.Title", "Manual.Safety.Body", "ShieldCheckOutline"),
        ("auto-register", "Manual.AutoRegister.Title", "Manual.AutoRegister.Body", "PhonePlusOutline"),
        ("datamoll", "Manual.Datamoll.Title", "Manual.Datamoll.Body", "CartOutline"),
        ("sending", "Manual.Sending.Title", "Manual.Sending.Body", "SendOutline"),
        ("engagement", "Manual.Engagement.Title", "Manual.Engagement.Body", "ThumbUpOutline"),
        ("automation", "Manual.Automation.Title", "Manual.Automation.Body", "CalendarClockOutline"),
        ("parsing", "Manual.Parsing.Title", "Manual.Parsing.Body", "MagnifyScan"),
        ("license-faq", "Manual.LicenseFaq.Title", "Manual.LicenseFaq.Body", "HelpCircleOutline"),
    ];

    [ObservableProperty]
    private string searchText = "";

    [ObservableProperty]
    private ManualCategoryItem? selectedCategory;

    [ObservableProperty]
    private bool noResults;

    public ObservableCollection<ManualCategoryItem> Categories { get; } = new();

    public ManualViewModel()
    {
        Rebuild();
        LocalizationService.Instance.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == "Item[]")
                Rebuild();
        };
    }

    partial void OnSearchTextChanged(string value) => Rebuild();

    private void Rebuild()
    {
        var previousKey = SelectedCategory?.Key;
        var mask = SearchText.Trim();

        var items = Definitions
            .Select(d => new ManualCategoryItem(d.Key, d.TitleKey, d.BodyKey, d.Icon))
            .Where(item => mask.Length == 0
                || item.Title.Contains(mask, StringComparison.OrdinalIgnoreCase)
                || item.Body.Contains(mask, StringComparison.OrdinalIgnoreCase))
            .ToList();

        Categories.Clear();
        foreach (var item in items)
            Categories.Add(item);

        SelectedCategory = Categories.FirstOrDefault(c => c.Key == previousKey) ?? Categories.FirstOrDefault();
        NoResults = Categories.Count == 0;
    }
}
