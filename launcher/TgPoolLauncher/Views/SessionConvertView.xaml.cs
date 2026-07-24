using System.Windows.Controls;
using TgPoolLauncher.ViewModels;

namespace TgPoolLauncher.Views;

public partial class SessionConvertView : UserControl
{
    public SessionConvertView(SessionConvertViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }
}
