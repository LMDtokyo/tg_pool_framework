using System.Collections.ObjectModel;
using System.Windows;
using CommunityToolkit.Mvvm.ComponentModel;
using TgPoolLauncher.Models;
using TgPoolLauncher.Services;

namespace TgPoolLauncher.ViewModels;

public partial class DashboardViewModel : ObservableObject
{
    [ObservableProperty]
    private bool connected;

    public ObservableCollection<AccountStatusRow> AccountStatuses { get; } = new();

    public DashboardViewModel(EventStreamClient eventStream)
    {
        eventStream.EventReceived += OnEventReceived;
        eventStream.ConnectionStateChanged += isConnected =>
            Application.Current.Dispatcher.Invoke(() => Connected = isConnected);
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
