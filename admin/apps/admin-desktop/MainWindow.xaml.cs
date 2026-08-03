using System.Windows;
using System.Windows.Controls;
using TgPoolAdmin.Services;
using TgPoolAdmin.ViewModels;

namespace TgPoolAdmin;

public partial class MainWindow : Window
{
    private readonly PaymentAdminViewModel _viewModel;

    public MainWindow(PaymentAdminViewModel viewModel)
    {
        InitializeComponent();
        _viewModel = viewModel;
        DataContext = viewModel;
    }

    private void AdminKeyBox_OnPasswordChanged(object sender, RoutedEventArgs e)
    {
        if (sender is PasswordBox box)
            _viewModel.AdminKey = box.Password;
    }

    private void WalletCard_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not Button { DataContext: AdminUser user })
            return;
        _viewModel.PrepareWithdrawal(user);
        new PaymentWithdrawalDialog(_viewModel) { Owner = this }.ShowDialog();
    }

    private void NavigationButton_Click(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement { Tag: string section })
            _viewModel.SelectSection(section);
    }

    private void CopyWalletAddress_Click(object sender, RoutedEventArgs e)
    {
        e.Handled = true;
        if (sender is Button { DataContext: AdminUser user } && !string.IsNullOrWhiteSpace(user.Address))
            Clipboard.SetText(user.Address);
    }

    private void MinimizeButton_Click(object sender, RoutedEventArgs e) =>
        WindowState = WindowState.Minimized;

    private void MaximizeButton_Click(object sender, RoutedEventArgs e) =>
        WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;

    private void CloseButton_Click(object sender, RoutedEventArgs e) => Close();
}
