using System.Windows.Controls;
using TgPoolLauncher.ViewModels;

namespace TgPoolLauncher.Views;

public partial class ManualView : UserControl
{
    public ManualView(ManualViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }
}
