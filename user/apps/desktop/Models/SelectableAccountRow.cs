using CommunityToolkit.Mvvm.ComponentModel;

namespace TgPoolLauncher.Models;

public sealed partial class SelectableAccountRow : ObservableObject
{
    public AccountDto Account { get; }

    [ObservableProperty]
    private bool isSelected;

    public SelectableAccountRow(AccountDto account)
    {
        Account = account;
    }
}
