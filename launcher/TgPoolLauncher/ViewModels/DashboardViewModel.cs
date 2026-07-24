using System.Collections.ObjectModel;
using System.Windows;
using CommunityToolkit.Mvvm.ComponentModel;
using TgPoolLauncher.Models;
using TgPoolLauncher.Services;

namespace TgPoolLauncher.ViewModels;

/// <summary>
/// Live campaign view: numeric progress mirrors CampaignViewModel.LatestStatus
/// (same DI-singleton instance, so no second polling loop); per-account status
/// rows come from the /ws/events feed via EventStreamClient.
/// </summary>
public partial class DashboardViewModel : ObservableObject
{
    private readonly CampaignViewModel _campaign;

    [ObservableProperty]
    private int total;

    [ObservableProperty]
    private int sent;

    [ObservableProperty]
    private int failed;

    [ObservableProperty]
    private bool running;

    [ObservableProperty]
    private bool connected;

    public ObservableCollection<AccountStatusRow> AccountStatuses { get; } = new();

    public DashboardViewModel(CampaignViewModel campaign, EventStreamClient eventStream)
    {
        _campaign = campaign;
        _campaign.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(CampaignViewModel.LatestStatus))
                ApplyStatus(_campaign.LatestStatus);
        };
        ApplyStatus(_campaign.LatestStatus);

        eventStream.EventReceived += OnEventReceived;
        eventStream.ConnectionStateChanged += isConnected =>
            Application.Current.Dispatcher.Invoke(() => Connected = isConnected);
    }

    private void ApplyStatus(CampaignStatusDto? status)
    {
        if (status is null)
            return;
        Total = status.Total;
        Sent = status.Sent;
        Failed = status.Failed;
        Running = status.Running;
    }

    // Fires from EventStreamClient's background receive loop -- must marshal
    // to the UI thread before touching ObservableCollection/bound properties.
    private void OnEventReceived(EventEnvelope envelope)
    {
        if (envelope.Type != "AccountStatusEvent")
            return;

        var phone = envelope.Data.GetProperty("phone").GetString() ?? "";
        var status = envelope.Data.GetProperty("status").GetString() ?? "";
        var detail = envelope.Data.TryGetProperty("detail", out var d) ? d.GetString() ?? "" : "";

        Application.Current.Dispatcher.Invoke(() =>
        {
            var row = AccountStatuses.FirstOrDefault(r => r.Phone == phone);
            if (row is null)
            {
                AccountStatuses.Add(new AccountStatusRow { Phone = phone, Status = status, Detail = detail });
            }
            else
            {
                row.Status = status;
                row.Detail = detail;
            }
        });
    }
}
