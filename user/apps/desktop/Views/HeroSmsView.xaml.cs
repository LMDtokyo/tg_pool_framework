using System.Windows.Controls;
using TgPoolLauncher.ViewModels;

namespace TgPoolLauncher.Views;

public partial class HeroSmsView : UserControl
{
    public HeroSmsView(HeroSmsViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
        viewModel.PropertyChanged += (_, args) =>
        {
            if (args.PropertyName == nameof(HeroSmsViewModel.TwoFactorPassword)
                && string.IsNullOrEmpty(viewModel.TwoFactorPassword)
                && TwoFactorPasswordBox.Password.Length > 0)
            {
                TwoFactorPasswordBox.Clear();
            }
        };
    }

    private void ApiKeyBox_OnPasswordChanged(object sender, System.Windows.RoutedEventArgs e)
    {
        if (DataContext is HeroSmsViewModel viewModel && sender is PasswordBox passwordBox)
            viewModel.ApiKey = passwordBox.Password;
    }

    private void TwoFactorPasswordBox_OnPasswordChanged(
        object sender, System.Windows.RoutedEventArgs e)
    {
        if (DataContext is HeroSmsViewModel viewModel && sender is PasswordBox passwordBox)
            viewModel.TwoFactorPassword = passwordBox.Password;
    }
}
