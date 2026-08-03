using System.Windows.Controls;
using TgPoolLauncher.ViewModels;

namespace TgPoolLauncher.Views;

public partial class JsonGeneratorView : UserControl
{
    public JsonGeneratorView(JsonGeneratorViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }
}
