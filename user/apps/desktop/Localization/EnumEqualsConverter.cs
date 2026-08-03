using System.Globalization;
using System.Windows.Data;

namespace TgPoolLauncher.Localization;

/// <summary>Used by the sidebar language toggle to highlight the active AppLanguage button.</summary>
public sealed class EnumEqualsConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        value?.ToString() == parameter?.ToString();

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}
