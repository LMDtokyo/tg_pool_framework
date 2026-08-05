using System.Windows;
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
        RoutedEventArgs e)
    {
        if (DataContext is DatamollViewModel viewModel && sender is PasswordBox passwordBox)
            viewModel.ApiKey = passwordBox.Password;
    }

    private void CopyDepositAddress_Click(object sender, RoutedEventArgs e)
    {
        if (DataContext is DatamollViewModel { DepositAddress.Length: > 0 } viewModel)
            Clipboard.SetText(viewModel.DepositAddress);
    }
}
