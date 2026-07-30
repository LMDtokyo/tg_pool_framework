using System.Windows.Controls;
using TgPoolLauncher.ViewModels;

namespace TgPoolLauncher.Views;

public partial class StoriesView : UserControl
{
    public StoriesView(StoriesViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }
}
