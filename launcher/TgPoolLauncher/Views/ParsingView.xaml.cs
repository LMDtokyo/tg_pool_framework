using System.Windows.Controls;
using TgPoolLauncher.ViewModels;

namespace TgPoolLauncher.Views;

public partial class ParsingView : UserControl
{
    public ParsingView(ParsingViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }
}
