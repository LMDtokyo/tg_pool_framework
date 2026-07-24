using System.Windows.Controls;
using TgPoolLauncher.ViewModels;

namespace TgPoolLauncher.Views;

public partial class ProxyCheckView : UserControl
{
    public ProxyCheckView(ProxyCheckViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }
}
