using CommunityToolkit.Mvvm.ComponentModel;
using TgPoolLauncher.Localization;
using TgPoolLauncher.Models;

namespace TgPoolLauncher.ViewModels;

/// <summary>
/// Holds the license status fetched once at startup (see App.xaml.cs's call to
/// LicenseGateway.SyncBackendAsync) so the sidebar can show a "days remaining"
/// countdown. Recomputes its display text on language switch the same way
/// ManualViewModel does, since "expires in N days" is itself translated text.
/// </summary>
public partial class LicenseStatusViewModel : ObservableObject
{
    private LicenseStatusDto? _status;

    [ObservableProperty]
    private string summaryText = "";

    [ObservableProperty]
    private string tierText = "";

    [ObservableProperty]
    private bool isExpiringSoon;

    [ObservableProperty]
    private bool isExpired;

    public LicenseStatusViewModel()
    {
        LocalizationService.Instance.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == "Item[]")
                Recompute();
        };
    }

    public void SetStatus(LicenseStatusDto? status)
    {
        _status = status;
        Recompute();
    }

    private void Recompute()
    {
        if (_status is null || !_status.Valid || _status.ExpiresAt is null)
        {
            SummaryText = LocalizationService.Instance["License.NoStatus"];
            TierText = "";
            IsExpiringSoon = false;
            IsExpired = false;
            return;
        }

        var daysLeft = (int)Math.Ceiling((_status.ExpiresAt.Value - DateTimeOffset.Now).TotalDays);
        IsExpired = daysLeft <= 0;
        IsExpiringSoon = !IsExpired && daysLeft <= 3;

        SummaryText = IsExpired
            ? LocalizationService.Instance["License.Expired"]
            : string.Format(LocalizationService.Instance[DaysLeftFormatKey(daysLeft)], daysLeft);

        TierText = string.IsNullOrWhiteSpace(_status.Tier) ? "" : _status.Tier.ToUpperInvariant();
    }

    /// <summary>
    /// Russian needs three plural forms (1 день / 2-4 дня / 5+ дней, with the usual
    /// 11-14 exception); English/Chinese just reuse whichever of the three keys they
    /// need since they don't inflect the same way -- see License.DaysLeftFormat* in
    /// CommonStrings.cs, where the EN/ZH text for "Few"/"Many" is identical.
    /// </summary>
    private static string DaysLeftFormatKey(int days)
    {
        var mod100 = days % 100;
        var mod10 = days % 10;
        if (mod10 == 1 && mod100 != 11)
            return "License.DaysLeftFormatOne";
        if (mod10 is >= 2 and <= 4 && mod100 is < 12 or > 14)
            return "License.DaysLeftFormatFew";
        return "License.DaysLeftFormatMany";
    }
}
