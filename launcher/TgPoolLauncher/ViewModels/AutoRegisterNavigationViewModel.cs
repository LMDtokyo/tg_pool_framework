using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using TgPoolLauncher.Models;
using TgPoolLauncher.Views;

namespace TgPoolLauncher.ViewModels;

public partial class AutoRegisterNavigationViewModel : ObservableObject
{
    public ObservableCollection<AutoRegisterPage> Pages { get; }
    public ObservableCollection<AutoRegisterPage> InvitePages { get; }
    public ObservableCollection<AutoRegisterPage> PhoneNumberPages { get; }

    [ObservableProperty]
    private AutoRegisterPage? selectedPage;

    public AutoRegisterNavigationViewModel(
        UniversalActivateView universalActivateView,
        HeroSmsView heroSmsView,
        SmsPoolView smsPoolView,
        GrizzlySmsView grizzlySmsView,
        DatamollView datamollView,
        InviteByNumberView inviteByNumberView,
        SendByNumbersView sendByNumbersView,
        NumberCheckerView numberCheckerView)
    {
        Pages =
        [
            new("universal-activate", "Universal (activate)", universalActivateView),
            new("hero-sms", "hero-sms", heroSmsView),
            new("sms-pool", "SMSpool", smsPoolView),
            new("grizzly-sms", "GrizzlySMS", grizzlySmsView),
            new("datamoll", "Datamoll", datamollView),
        ];
        InvitePages =
        [
            new("invite-by-number", "Invite by number", inviteByNumberView),
        ];
        PhoneNumberPages =
        [
            new("send-by-numbers", "Send by numbers", sendByNumbersView),
            new("number-checker", "Number checker", numberCheckerView),
        ];

        SelectedPage = Pages[0];
    }
}
