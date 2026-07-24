using System.Windows.Data;
using System.Windows.Markup;

namespace TgPoolLauncher.Localization.Markup;

/// <summary>
/// XAML sugar for a translated string: <c>Text="{loc:Tr SomeKey}"</c> expands to a
/// one-way Binding against <see cref="LocalizationService"/>'s indexer, so it updates
/// automatically whenever the current language changes.
/// </summary>
[MarkupExtensionReturnType(typeof(object))]
public sealed class TrExtension : MarkupExtension
{
    public TrExtension()
    {
    }

    public TrExtension(string key)
    {
        Key = key;
    }

    [ConstructorArgument("key")]
    public string Key { get; set; } = "";

    public override object ProvideValue(IServiceProvider serviceProvider)
    {
        var binding = new Binding($"[{Key}]")
        {
            Source = LocalizationService.Instance,
            Mode = BindingMode.OneWay,
        };
        return binding.ProvideValue(serviceProvider);
    }
}
