namespace TgPoolLauncher.Models;

/// <summary>
/// One row of the "Действия программы" live log, built from MessageDeliveredEvent
/// on the /ws/events feed (src/monitoring/event_bus.py). The event carries no message
/// text or timestamp, so Time is stamped on receipt and Message summarizes the
/// recipient + outcome rather than quoting content that was never sent over the wire.
/// </summary>
public sealed record CampaignLogRow(string Time, string Account, string Message, bool Success);
