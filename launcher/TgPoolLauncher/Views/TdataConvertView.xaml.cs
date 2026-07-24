using System.Windows.Controls;
using TgPoolLauncher.ViewModels;

namespace TgPoolLauncher.Views;

public partial class TdataConvertView : UserControl
{
    public TdataConvertView(TdataConvertViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }
}
