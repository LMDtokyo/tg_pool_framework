using System.Windows;
using TgPoolAdmin.Services;
using TgPoolAdmin.ViewModels;

namespace TgPoolAdmin;

public partial class App : Application
{
    private AdminApiClient? _apiClient;

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        try
        {
            _apiClient = new AdminApiClient(AdminApiClient.ResolveBaseUri());
            var viewModel = new PaymentAdminViewModel(_apiClient);
            MainWindow = new MainWindow(viewModel);
            MainWindow.Show();
        }
        catch (Exception exception)
        {
            MessageBox.Show(
                exception.Message,
                "TgPoolAdmin configuration error",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
            Shutdown(1);
        }
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _apiClient?.Dispose();
        base.OnExit(e);
    }
}
