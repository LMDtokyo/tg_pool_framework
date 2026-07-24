using System.Collections.ObjectModel;
using System.Text;
using System.Text.RegularExpressions;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace TgPoolLauncher.ViewModels;

public partial class TextRandomizerViewModel : ObservableObject
{
    private static readonly Regex MaskRegex = new(@"\{([^{}|]+(?:\|[^{}|]+)+)\}", RegexOptions.Compiled);

    private const string RuToEnTemplate = "{a|а}, {A|А}, {B|В}, {e|е}, {E|Е}, {K|К}, {M|М}, {H|Н}, {o|о}, {O|О}, {p|р}, {P|Р}, {c|с}, {C|С}, {T|Т}, {x|х}, {X|Х}";
    private const string EnToRuTemplate = "{а|a}, {А|A}, {В|B}, {е|e}, {Е|E}, {К|K}, {М|M}, {Н|H}, {о|o}, {О|O}, {р|p}, {Р|P}, {с|c}, {С|C}, {Т|T}, {х|x}, {Х|X}";

    [ObservableProperty]
    private string template = RuToEnTemplate;

    [ObservableProperty]
    private string mainText = string.Empty;

    [ObservableProperty]
    private string resultText = string.Empty;

    [ObservableProperty]
    private bool isEnToRu;

    [ObservableProperty]
    private string statusMessage = "Template is ready.";

    public ObservableCollection<TemplateMask> Masks { get; } = new();

    public TextRandomizerViewModel()
    {
        RefreshMasks();
    }

    partial void OnIsEnToRuChanged(bool value)
    {
        Template = value ? EnToRuTemplate : RuToEnTemplate;
        RefreshMasks();
    }

    [RelayCommand]
    private void Check()
    {
        RefreshMasks();
        StatusMessage = Masks.Count == 0
            ? "No valid masks found. Use spin syntax like {O|0}."
            : $"{Masks.Count} masks are ready.";
    }

    [RelayCommand]
    private void CreateRandomization()
    {
        RefreshMasks();
        if (Masks.Count == 0)
        {
            ResultText = MainText;
            StatusMessage = "No masks were applied.";
            return;
        }

        ResultText = ApplyMasks(MainText, Masks);
        StatusMessage = "Randomization created.";
    }

    [RelayCommand]
    private void ResolveRandomization()
    {
        var source = string.IsNullOrEmpty(ResultText) ? ApplyMasks(MainText, Masks) : ResultText;
        ResultText = ResolveSpinSyntax(source);
        StatusMessage = "One randomized version created.";
    }

    private void RefreshMasks()
    {
        Masks.Clear();
        var seen = new HashSet<string>();
        foreach (Match match in MaskRegex.Matches(Template))
        {
            var options = match.Groups[1].Value
                .Split('|', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .Where(option => option.Length > 0)
                .ToArray();
            if (options.Length < 2)
                continue;

            var source = options[0];
            if (!seen.Add(source))
                continue;

            Masks.Add(new TemplateMask(source, "{" + string.Join("|", options) + "}"));
        }
    }

    private static string ApplyMasks(string text, IEnumerable<TemplateMask> masks)
    {
        if (string.IsNullOrEmpty(text))
            return string.Empty;

        var lookup = masks.ToDictionary(mask => mask.Source, mask => mask.Mask);
        var builder = new StringBuilder(text.Length);
        foreach (var rune in text.EnumerateRunes())
        {
            var current = rune.ToString();
            builder.Append(lookup.TryGetValue(current, out var replacement) ? replacement : current);
        }
        return builder.ToString();
    }

    private static string ResolveSpinSyntax(string text)
    {
        var random = Random.Shared;
        return MaskRegex.Replace(text, match =>
        {
            var options = match.Groups[1].Value.Split('|', StringSplitOptions.TrimEntries);
            return options[random.Next(options.Length)];
        });
    }
}

public sealed record TemplateMask(string Source, string Mask);
