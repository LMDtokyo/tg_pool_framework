using System.Windows;
using System.Windows.Input;
using TgPoolAdmin.ViewModels;

namespace TgPoolAdmin;

public partial class PaymentWithdrawalDialog : Window
{
    public PaymentWithdrawalDialog(PaymentAdminViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }

    private void CopyWalletAddress_OnClick(object sender, RoutedEventArgs e)
    {
        if (DataContext is PaymentAdminViewModel { SelectedUser.Address: { Length: > 0 } address })
            Clipboard.SetText(address);
    }

    private void TitleBar_OnMouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ButtonState == MouseButtonState.Pressed)
            DragMove();
    }

    private void CloseButton_OnClick(object sender, RoutedEventArgs e) => Close();
}
