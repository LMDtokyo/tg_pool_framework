using CommunityToolkit.Mvvm.ComponentModel;

namespace TgPoolLauncher.Models;

public sealed partial class SelectableSourceRow : ObservableObject
{
    public ParseSourceOut Source { get; }

    [ObservableProperty]
    private bool isSelected;

    public SelectableSourceRow(ParseSourceOut source)
    {
        Source = source;
    }
}
