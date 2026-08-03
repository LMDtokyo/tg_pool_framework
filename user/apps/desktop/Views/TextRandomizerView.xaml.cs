using System.Windows.Controls;
using TgPoolLauncher.ViewModels;

namespace TgPoolLauncher.Views;

public partial class TextRandomizerView : UserControl
{
    public TextRandomizerView(TextRandomizerViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }
}
