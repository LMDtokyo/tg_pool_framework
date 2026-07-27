using System.Globalization;
using System.Windows.Data;
using TgPoolLauncher.Localization;

namespace TgPoolLauncher.Converters;

/// <summary>Maps a ParseSourceOut.Kind string ("channel"/"supergroup"/"chat") to its localized label.</summary>
public sealed class ParsingSourceKindConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        (value as string) switch
        {
            "channel" => LocalizationService.Instance["Parsing.SourceKindChannel"],
            "supergroup" => LocalizationService.Instance["Parsing.SourceKindSupergroup"],
            "chat" => LocalizationService.Instance["Parsing.SourceKindChat"],
            _ => value ?? "",
        };

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}
