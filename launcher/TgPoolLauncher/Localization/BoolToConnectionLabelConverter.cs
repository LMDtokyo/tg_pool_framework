using System.Globalization;
using System.Windows.Data;

namespace TgPoolLauncher.Localization;

/// <summary>
/// Multi-value so a language switch alone re-triggers it: Connected changes rarely (only on
/// actual socket connect/disconnect), so a plain IValueConverter bound to Connected would
/// leave this word frozen in whatever language was active the last time Connected flipped.
/// The second binding (CurrentLanguage) is otherwise unused -- its only job is to appear in
/// the MultiBinding's dependency list so LocalizationService's language-change notification
/// forces a re-convert.
/// </summary>
public sealed class BoolToConnectionLabelConverter : IMultiValueConverter
{
    public object Convert(object[] values, Type targetType, object? parameter, CultureInfo culture) =>
        LocalizationService.Instance[values.Length > 0 && values[0] is true ? "Dashboard.Connected" : "Dashboard.Disconnected"];

    public object[] ConvertBack(object? value, Type[] targetTypes, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}
