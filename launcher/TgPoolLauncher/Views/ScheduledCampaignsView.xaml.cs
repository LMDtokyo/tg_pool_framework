using System.Windows.Controls;
using TgPoolLauncher.ViewModels;

namespace TgPoolLauncher.Views;

public partial class ScheduledCampaignsView : UserControl
{
    public ScheduledCampaignsView(ScheduledCampaignsViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }
}
