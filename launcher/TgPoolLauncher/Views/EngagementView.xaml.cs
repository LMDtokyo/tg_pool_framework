using System.Windows.Controls;
using TgPoolLauncher.ViewModels;

namespace TgPoolLauncher.Views;

public partial class EngagementView : UserControl
{
    public EngagementView(EngagementViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }
}
