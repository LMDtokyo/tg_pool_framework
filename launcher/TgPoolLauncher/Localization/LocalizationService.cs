using System.ComponentModel;
using System.IO;
using System.Text.Json;
using TgPoolLauncher.Localization.Strings;
using TgPoolLauncher.Services;

namespace TgPoolLauncher.Localization;

/// <summary>
/// Singleton translation table. XAML reads through it via the indexer (see
/// <see cref="Markup.TrExtension"/>) which is bound with a plain WPF Binding --
/// switching <see cref="CurrentLanguage"/> raises a PropertyChanged for the
/// special "Item[]" name, which is WPF's documented signal to re-pull every
/// active indexer binding, so the whole app (including tabs not currently
/// visible, since their bindings stay alive off-screen) updates instantly.
/// </summary>
public sealed class LocalizationService : INotifyPropertyChanged
{
    public static LocalizationService Instance { get; } = new();

    private readonly Dictionary<AppLanguage, Dictionary<string, string>> _table = new()
    {
        [AppLanguage.Ru] = new(),
        [AppLanguage.En] = new(),
        [AppLanguage.Zh] = new(),
    };

    private AppLanguage _current;

    private LocalizationService()
    {
        CommonStrings.Register(_table);
        DashboardStrings.Register(_table);
        AccountsStrings.Register(_table);
        ProxyStrings.Register(_table);
        ToolsStrings.Register(_table);

        _current = LoadSavedLanguage();
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public AppLanguage CurrentLanguage
    {
        get => _current;
        set
        {
            if (_current == value)
                return;

            _current = value;
            SaveLanguage(value);
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(CurrentLanguage)));
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs("Item[]"));
        }
    }

    public string this[string key] =>
        _table[_current].TryGetValue(key, out var value) ? value : key;

    public string Translate(string key) => this[key];

    private static string SettingsPath => Path.Combine(AppPaths.Data, "ui_settings.json");

    private static AppLanguage LoadSavedLanguage()
    {
        try
        {
            if (File.Exists(SettingsPath))
            {
                var json = File.ReadAllText(SettingsPath);
                var doc = JsonSerializer.Deserialize<UiSettings>(json);
                if (doc is not null && Enum.TryParse<AppLanguage>(doc.Language, ignoreCase: true, out var lang))
                    return lang;
            }
        }
        catch
        {
            // best-effort -- fall back to default below
        }
        return AppLanguage.Ru;
    }

    private static void SaveLanguage(AppLanguage language)
    {
        try
        {
            var json = JsonSerializer.Serialize(new UiSettings { Language = language.ToString() });
            File.WriteAllText(SettingsPath, json);
        }
        catch
        {
            // best-effort -- language choice just won't persist across restarts
        }
    }

    private sealed class UiSettings
    {
        public string Language { get; set; } = nameof(AppLanguage.Ru);
    }
}
