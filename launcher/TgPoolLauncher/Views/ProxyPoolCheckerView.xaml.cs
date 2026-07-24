using System.Windows.Controls;
using TgPoolLauncher.ViewModels;

namespace TgPoolLauncher.Views;

public partial class ProxyPoolCheckerView : UserControl
{
    public ProxyPoolCheckerView(ProxyPoolCheckerViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }
}
