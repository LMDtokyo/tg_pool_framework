using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using TgPoolLauncher.ViewModels;

namespace TgPoolLauncher.Views;

public partial class AccountsView : UserControl
{
    public AccountsView(AccountsViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }

    private async void AccountsView_Loaded(object sender, RoutedEventArgs e)
    {
        if (DataContext is AccountsViewModel vm)
            await vm.LoadCommand.ExecuteAsync(null);
    }

    private void TableCard_SizeChanged(object sender, SizeChangedEventArgs e)
    {
        var border = (Border)sender;
        border.Clip = new RectangleGeometry(new Rect(0, 0, border.ActualWidth, border.ActualHeight))
        {
            RadiusX = 12,
            RadiusY = 12,
        };
    }
}
