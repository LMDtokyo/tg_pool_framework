using System.Globalization;
using System.Windows;
using System.Windows.Data;
using System.Windows.Media;
using TgPoolLauncher.Localization;
using TgPoolLauncher.Models;

namespace TgPoolLauncher.Converters;

internal readonly record struct StatusStyle(string LabelKey, string Background, string Foreground);

internal static class StatusPresentation
{
    private static readonly (string Key, StatusStyle Style)[] Entries =
    [
        ("alive", new StatusStyle("Status.Alive", "#2416A34A", "#4ADE80")),
        ("banned", new StatusStyle("Status.Banned", "#24EF4444", "#F87171")),
        ("unauthorized", new StatusStyle("Status.Unauthorized", "#26FFFFFF", "#D1D5DB")),
        ("spamblock", new StatusStyle("Status.Spamblock", "#24F59E0B", "#FBBF24")),
        ("frozen", new StatusStyle("Status.Frozen", "#243B82F6", "#60A5FA")),
        ("flood", new StatusStyle("Status.Flood", "#24F97316", "#FB923C")),
        ("proxy_dead", new StatusStyle("Status.ProxyDead", "#24DC2626", "#F87171")),
        ("unknown", new StatusStyle("Status.Unknown", "#26FFFFFF", "#D1D5DB")),
    ];

    private static readonly Dictionary<string, StatusStyle> Styles =
        Entries.ToDictionary(e => e.Key, e => e.Style);

    private static readonly StatusStyle Fallback = new("Status.Unknown", "#26FFFFFF", "#D1D5DB");

    public static StatusStyle For(object? status) =>
        status is string key && Styles.TryGetValue(key, out var style) ? style : Fallback;

    public static IReadOnlyList<(string Value, string LabelKey)> AllOptions { get; } =
        Entries.Select(e => (e.Key, e.Style.LabelKey)).ToArray();
}

public sealed class StatusToLabelConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        LocalizationService.Instance[StatusPresentation.For(value).LabelKey];

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

public sealed class StatusToBackgroundBrushConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        BrushCache.Get(StatusPresentation.For(value).Background);

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

public sealed class StatusToForegroundBrushConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        BrushCache.Get(StatusPresentation.For(value).Foreground);

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

internal static class BrushCache
{
    private static readonly Dictionary<string, SolidColorBrush> Cache = new();

    public static SolidColorBrush Get(string hex)
    {
        if (Cache.TryGetValue(hex, out var cached))
            return cached;

        var brush = new SolidColorBrush((Color)ColorConverter.ConvertFromString(hex));
        brush.Freeze();
        Cache[hex] = brush;
        return brush;
    }
}

public sealed class CountryToFlagConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        if (value is not string code || code.Length != 2)
            return "—";

        var upper = code.ToUpperInvariant();
        var flag = string.Concat(upper.Select(ToRegionalIndicator));
        return $"{flag} {upper}";
    }

    private static string ToRegionalIndicator(char letter) =>
        char.ConvertFromUtf32(0x1F1E6 + (letter - 'A'));

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

public sealed class InitialsConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        if (value is not AccountDto account)
            return "?";

        if (!string.IsNullOrWhiteSpace(account.FirstName))
            return account.FirstName.Trim()[..1].ToUpperInvariant();

        var handle = account.Username?.TrimStart('@');
        if (!string.IsNullOrWhiteSpace(handle))
            return handle[..1].ToUpperInvariant();

        return account.Phone.Length >= 2 ? account.Phone[^2..] : "?";
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

public sealed class NameToAvatarBrushConverter : IValueConverter
{
    private static readonly string[] Palette =
    [
        "#F87171", "#FB923C", "#FBBF24", "#4ADE80",
        "#34D399", "#22D3EE", "#60A5FA", "#A78BFA",
        "#F472B6", "#38BDF8",
    ];

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        var key = value is AccountDto account ? account.Phone : value?.ToString() ?? "";
        var index = Math.Abs(key.GetHashCode()) % Palette.Length;
        return BrushCache.Get(Palette[index]);
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

public sealed class ProxyUsageLabelConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        if (value is not AccountDto account || !account.UsesProxy)
            return LocalizationService.Instance["Accounts.ProxyDirect"];

        if (!string.IsNullOrWhiteSpace(account.ProxyLabel))
            return account.ProxyLabel;

        if (account.Proxy is { IsActive: true })
            return LocalizationService.Instance["Accounts.ProxyCheckedActive"];

        if (account.Proxy is { IsActive: false })
            return LocalizationService.Instance["Accounts.ProxyCheckedDead"];

        return LocalizationService.Instance["Accounts.ProxyConfigured"];
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

public sealed class ProxyUsageForegroundBrushConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        if (value is not AccountDto account || !account.UsesProxy)
            return BrushCache.Get("#9CA3AF");

        if (string.Equals(account.ProxyStatus, "bad", StringComparison.OrdinalIgnoreCase))
            return BrushCache.Get("#F87171");

        if (account.Proxy is { IsActive: false })
            return BrushCache.Get("#F87171");

        return BrushCache.Get("#4ADE80");
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

public sealed class ProxyUsageTooltipConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        if (value is not AccountDto account || !account.UsesProxy)
            return LocalizationService.Instance["Accounts.ProxyDirectTooltip"];

        var label = string.IsNullOrWhiteSpace(account.ProxyLabel)
            ? LocalizationService.Instance["Accounts.ProxyConfigured"]
            : account.ProxyLabel;

        if (account.Proxy is { IsActive: true } proxy)
            return $"{label} - {proxy.LatencyMs:0} ms";

        if (account.Proxy is { IsActive: false } deadProxy && !string.IsNullOrWhiteSpace(deadProxy.ErrorMessage))
            return $"{label} - {deadProxy.ErrorMessage}";

        return label;
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

public sealed class RelativeAgeConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        if (value is not DateTimeOffset since)
            return "—";

        var days = (int)(DateTimeOffset.UtcNow - since).TotalDays;
        if (days < 0)
            days = 0;

        var loc = LocalizationService.Instance;
        var daysSuffix = loc["Time.DaysSuffix"];
        var monthsSuffix = loc["Time.MonthsSuffix"];
        var yearsSuffix = loc["Time.YearsSuffix"];

        if (days < 30)
            return $"{days} {daysSuffix}";

        if (days < 365)
        {
            var months = days / 30;
            var remDays = days - months * 30;
            return remDays > 0 ? $"{months} {monthsSuffix} {remDays} {daysSuffix}" : $"{months} {monthsSuffix}";
        }

        var years = days / 365;
        var remMonths = (days - years * 365) / 30;
        return remMonths > 0 ? $"{years} {yearsSuffix} {remMonths} {monthsSuffix}" : $"{years} {yearsSuffix}";
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

public sealed class RelativeTimeConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        if (value is not DateTimeOffset when)
            return "—";

        var local = when.ToLocalTime();
        var now = DateTimeOffset.Now;
        var time = local.ToString("HH:mm", culture);

        if (local.Date == now.Date)
            return $"{LocalizationService.Instance["Time.Today"]}, {time}";
        if (local.Date == now.Date.AddDays(-1))
            return $"{LocalizationService.Instance["Time.Yesterday"]}, {time}";

        return local.ToString("dd.MM.yyyy", culture);
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

public sealed class IndexPlusOneConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        value is int index ? (index + 1).ToString(culture) : "";

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

/// <summary>
/// Empty string -> Visible, non-empty -> Collapsed. Pass ConverterParameter="Invert" for
/// the opposite (used to show an error TextBlock only once StatusMessage is non-empty).
/// </summary>
public sealed class EmptyStringToVisibilityConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        var isEmpty = string.IsNullOrEmpty(value as string);
        var invert = string.Equals(parameter as string, "Invert", StringComparison.OrdinalIgnoreCase);
        return isEmpty != invert ? Visibility.Visible : Visibility.Collapsed;
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

/// <summary>Any reference type: null -> Collapsed, non-null -> Visible. Unlike
/// EmptyStringToVisibilityConverter, works for non-string bindings (e.g. a stats dictionary).</summary>
public sealed class NullToVisibilityConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        value is null ? Visibility.Collapsed : Visibility.Visible;

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}
