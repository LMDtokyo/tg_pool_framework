using System.Diagnostics;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using TgPoolLauncher.Models;
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

    private void OpenAccountFolderButton_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not FrameworkElement element || element.DataContext is not SelectableAccountRow row)
            return;

        var rawPath = row.Account.SessionPath;
        if (string.IsNullOrWhiteSpace(rawPath))
            return;

        // The backend builds this path with a forward slash before the filename
        // (Python's f"{session_dir}/{name}") on top of a backslash-separated
        // Windows session_dir. .NET's File.Exists tolerates that mix fine, but
        // explorer.exe's own /select argument parser doesn't -- it silently
        // fails to resolve the target and opens some unrelated default folder
        // instead. GetFullPath normalizes to pure backslashes and resolves the
        // path to absolute, so this is the value both the existence check and
        // Explorer itself operate on.
        var sessionPath = Path.GetFullPath(rawPath);
        try
        {
            if (File.Exists(sessionPath))
            {
                // /select highlights the account's own session file in Explorer,
                // instead of just dropping the user into the shared accounts
                // folder with hundreds of other sessions to hunt through.
                Process.Start(new ProcessStartInfo("explorer.exe", $"/select,\"{sessionPath}\""));
            }
            else if (Directory.Exists(Path.GetDirectoryName(sessionPath)))
            {
                Process.Start(new ProcessStartInfo(Path.GetDirectoryName(sessionPath)!) { UseShellExecute = true });
            }
        }
        catch
        {
            // best-effort -- a failed Explorer launch must not disrupt the rest of the UI
        }
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
