using System.Windows.Controls;
using TgPoolLauncher.ViewModels;

namespace TgPoolLauncher.Views;

public partial class DashboardView : UserControl
{
    public DashboardView(DashboardViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }
}
