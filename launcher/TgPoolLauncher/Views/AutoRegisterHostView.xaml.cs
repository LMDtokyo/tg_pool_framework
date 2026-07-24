using System.Windows.Controls;
using TgPoolLauncher.ViewModels;

namespace TgPoolLauncher.Views;

public partial class AutoRegisterHostView : UserControl
{
    public AutoRegisterHostView(AutoRegisterNavigationViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }
}
