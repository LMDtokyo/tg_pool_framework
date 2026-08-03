using System.Windows.Controls;
using TgPoolLauncher.ViewModels;

namespace TgPoolLauncher.Views;

public partial class DatamollView : UserControl
{
    public DatamollView(DatamollViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }

    private void ApiKeyBox_OnPasswordChanged(
        object sender,
        System.Windows.RoutedEventArgs e)
    {
        if (DataContext is DatamollViewModel viewModel && sender is PasswordBox passwordBox)
            viewModel.ApiKey = passwordBox.Password;
    }
}
