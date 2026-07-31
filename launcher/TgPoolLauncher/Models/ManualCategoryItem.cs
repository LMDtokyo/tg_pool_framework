namespace TgPoolLauncher.Models;

/// <summary>
/// One knowledge-base entry on the Manual tab. Title/Body are localization
/// keys (see Localization/Strings/ManualStrings.cs), resolved at display time
/// so the whole manual re-renders on a language switch like everything else.
/// </summary>
public sealed record ManualCategoryItem(string Key, string TitleKey, string BodyKey, string Icon)
{
    public string Title => Localization.LocalizationService.Instance[TitleKey];
    public string Body => Localization.LocalizationService.Instance[BodyKey];
}
