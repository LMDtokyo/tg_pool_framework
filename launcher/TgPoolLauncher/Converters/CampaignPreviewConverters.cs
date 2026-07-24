using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Documents;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using MahApps.Metro.IconPacks;
using TgPoolLauncher.Localization;

namespace TgPoolLauncher.Converters;

public sealed record PreviewButton(string Text, string Url);

/// <summary>
/// Renders MessageText through a small Telegram-markup approximation (bold/italic/code/links,
/// both "markdown" and "html" parse modes) into a ready-made TextBlock. Returning the element
/// itself -- rather than a plain string -- is the simplest way to bind rich Inlines from a
/// converter without a dedicated attached-property/behavior.
/// </summary>
public sealed class MessageMarkupToInlinesConverter : IMultiValueConverter
{
    private static readonly Regex MarkdownPattern = new(
        @"\*(?<b>[^*\n]+)\*|_(?<i>[^_\n]+)_|`(?<c>[^`\n]+)`|\[(?<a>[^\]\n]+)\]\((?<u>[^)\n]+)\)",
        RegexOptions.Compiled);

    private static readonly Regex HtmlPattern = new(
        "<b>(?<b>.*?)</b>|<strong>(?<b>.*?)</strong>|<i>(?<i>.*?)</i>|<em>(?<i>.*?)</em>|" +
        "<code>(?<c>.*?)</code>|<a\\s+href=\"(?<u>[^\"]*)\"\\s*>(?<a>.*?)</a>",
        RegexOptions.Compiled | RegexOptions.Singleline);

    public object Convert(object[] values, Type targetType, object? parameter, CultureInfo culture)
    {
        var text = values.Length > 0 ? values[0] as string : null;
        var mode = values.Length > 1 ? values[1] as string : "markdown";

        var block = new TextBlock
        {
            TextWrapping = TextWrapping.Wrap,
            FontSize = 14,
            Foreground = Brush("TextPrimaryBrush"),
        };

        if (string.IsNullOrWhiteSpace(text))
        {
            block.Inlines.Add(new Run(LocalizationService.Instance["Common.MessagePreviewPlaceholder"])
            {
                Foreground = Brush("TextFaintBrush"),
                FontStyle = FontStyles.Italic,
            });
            return block;
        }

        AppendFormatted(block.Inlines, text, mode ?? "markdown");
        return block;
    }

    public object[] ConvertBack(object value, Type[] targetTypes, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();

    private static void AppendFormatted(InlineCollection inlines, string text, string mode)
    {
        var isHtml = string.Equals(mode, "html", StringComparison.OrdinalIgnoreCase);
        var regex = isHtml ? HtmlPattern : MarkdownPattern;
        var codeBackground = Brush("SurfaceAltBrush");
        var linkBrush = Brush("AccentHoverBrush");

        var pos = 0;
        foreach (Match m in regex.Matches(text))
        {
            if (m.Index > pos)
                AppendPlain(inlines, text[pos..m.Index]);

            if (m.Groups["b"].Success)
                inlines.Add(new Bold(new Run(m.Groups["b"].Value)));
            else if (m.Groups["i"].Success)
                inlines.Add(new Italic(new Run(m.Groups["i"].Value)));
            else if (m.Groups["c"].Success)
                inlines.Add(new Run(m.Groups["c"].Value) { FontFamily = new FontFamily("Consolas"), Background = codeBackground });
            else if (m.Groups["a"].Success)
                inlines.Add(new Run(m.Groups["a"].Value) { Foreground = linkBrush, TextDecorations = TextDecorations.Underline });

            pos = m.Index + m.Length;
        }

        if (pos < text.Length)
            AppendPlain(inlines, text[pos..]);
    }

    private static void AppendPlain(InlineCollection inlines, string text)
    {
        var lines = text.Split('\n');
        for (var i = 0; i < lines.Length; i++)
        {
            if (i > 0) inlines.Add(new LineBreak());
            if (lines[i].Length > 0) inlines.Add(new Run(lines[i]));
        }
    }

    internal static Brush Brush(string resourceKey) => (Brush)Application.Current.Resources[resourceKey];
}

/// <summary>
/// Parses the app's own "[Текст | https://url]" button DSL (rows separated by a literal
/// "\n" the user types, since the field is a single-line TextBox) into preview rows.
/// </summary>
public sealed class ButtonsRawToRowsConverter : IValueConverter
{
    private static readonly Regex ButtonPattern = new(@"\[(?<text>[^\|\]]+)\|(?<url>[^\]]+)\]", RegexOptions.Compiled);

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        var rows = new List<List<PreviewButton>>();
        if (value is not string raw || string.IsNullOrWhiteSpace(raw))
            return rows;

        foreach (var rowRaw in raw.Split(["\\n"], StringSplitOptions.None))
        {
            var row = ButtonPattern.Matches(rowRaw)
                .Select(m => new PreviewButton(m.Groups["text"].Value.Trim(), m.Groups["url"].Value.Trim()))
                .Where(b => b.Text.Length > 0)
                .ToList();
            if (row.Count > 0)
                rows.Add(row);
        }
        return rows;
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

/// <summary>
/// Local media path -> a thumbnail if it's a readable image, otherwise a generic file chip.
/// Never throws: an unreadable/missing/corrupt path just falls back to the chip.
/// </summary>
public sealed class MediaPathToPreviewConverter : IValueConverter
{
    private static readonly HashSet<string> ImageExtensions =
        new(StringComparer.OrdinalIgnoreCase) { ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp" };

    public object? Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        if (value is not string path || string.IsNullOrWhiteSpace(path))
            return null;

        if (ImageExtensions.Contains(Path.GetExtension(path)) && File.Exists(path))
        {
            try
            {
                var bitmap = new BitmapImage();
                bitmap.BeginInit();
                bitmap.CacheOption = BitmapCacheOption.OnLoad;
                bitmap.UriSource = new Uri(Path.GetFullPath(path));
                bitmap.EndInit();
                bitmap.Freeze();
                return new Border
                {
                    CornerRadius = new CornerRadius(8),
                    ClipToBounds = true,
                    Child = new Image { Source = bitmap, Stretch = Stretch.UniformToFill, Height = 180 },
                };
            }
            catch (Exception)
            {
                // Extension looked like an image but the file didn't decode -- fall through.
            }
        }

        var chip = new Border
        {
            Background = MessageMarkupToInlinesConverter.Brush("SurfaceAltBrush"),
            BorderBrush = MessageMarkupToInlinesConverter.Brush("BorderBrush"),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(8),
            Padding = new Thickness(10, 8, 10, 8),
        };
        var row = new StackPanel { Orientation = Orientation.Horizontal };
        row.Children.Add(new PackIconMaterial
        {
            Kind = PackIconMaterialKind.Paperclip,
            Width = 14,
            Height = 14,
            Foreground = MessageMarkupToInlinesConverter.Brush("TextMutedBrush"),
            Margin = new Thickness(0, 0, 8, 0),
            VerticalAlignment = VerticalAlignment.Center,
        });
        row.Children.Add(new TextBlock
        {
            Text = Path.GetFileName(path),
            Foreground = MessageMarkupToInlinesConverter.Brush("TextMutedBrush"),
            FontSize = 12,
            VerticalAlignment = VerticalAlignment.Center,
            TextTrimming = TextTrimming.CharacterEllipsis,
        });
        chip.Child = row;
        return chip;
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}

public sealed class FirstLetterConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        var text = (value as string)?.TrimStart('@', ' ');
        return string.IsNullOrEmpty(text) ? "?" : text[..1].ToUpperInvariant();
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) =>
        throw new NotSupportedException();
}
