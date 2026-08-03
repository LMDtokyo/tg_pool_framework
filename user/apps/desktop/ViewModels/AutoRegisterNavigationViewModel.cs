using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using TgPoolLauncher.Models;
using TgPoolLauncher.Views;

namespace TgPoolLauncher.ViewModels;

public partial class AutoRegisterNavigationViewModel : ObservableObject
{
    public ObservableCollection<AutoRegisterPage> Pages { get; }
    public ObservableCollection<AutoRegisterPage> InvitePages { get; }
    public ObservableCollection<AutoRegisterPage> SendingSmsPages { get; }

    [ObservableProperty]
    private AutoRegisterPage? selectedPage;

    public AutoRegisterNavigationViewModel(
        DatamollView datamollView,
        InviteByNumberView inviteByNumberView,
        SendingSmsByIdView sendingSmsByIdView,
        SendByNumbersView sendByNumbersView,
        NumberCheckerView numberCheckerView,
        ScheduledCampaignsView scheduledCampaignsView)
    {
        Pages =
        [
            new("datamoll", "Andromeda service", datamollView),
        ];
        InvitePages =
        [
            new("invite-by-number", "Invite by number", inviteByNumberView),
        ];
        SendingSmsPages =
        [
            new("sending-sms-by-id", "Sending SMS by ID", sendingSmsByIdView),
            new("send-by-numbers", "Send by numbers", sendByNumbersView),
            new("number-checker", "Number checker", numberCheckerView),
            new("scheduled-campaigns", "Scheduled campaigns", scheduledCampaignsView),
        ];

        SelectedPage = Pages[0];
    }
}
