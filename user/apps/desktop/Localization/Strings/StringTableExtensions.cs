namespace TgPoolLauncher.Localization.Strings;

internal static class StringTableExtensions
{
    public static void Add(
        this Dictionary<AppLanguage, Dictionary<string, string>> table,
        string key, string ru, string en, string zh)
    {
        table[AppLanguage.Ru][key] = ru;
        table[AppLanguage.En][key] = en;
        table[AppLanguage.Zh][key] = zh;
    }
}
