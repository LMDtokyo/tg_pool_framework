using System.Text.Json;
using System.Text.Json.Serialization;
using CommunityToolkit.Mvvm.ComponentModel;

namespace TgPoolLauncher.Models;

/// <summary>
/// Mirrors src/api/events.py's _serialize() output: {"type": "...", "data": {...}}.
/// Data is kept as a raw JsonElement since its shape depends on Type
/// (AccountStatusEvent / MessageDeliveredEvent / MetricUpdateEvent).
/// </summary>
public sealed class EventEnvelope
{
    [JsonPropertyName("type")]
    public string Type { get; init; } = "";

    [JsonPropertyName("data")]
    public JsonElement Data { get; init; }
}

/// <summary>
/// ObservableObject (not a plain POCO) so in-place Status/Detail updates on an
/// existing row raise PropertyChanged -- an ObservableCollection only notifies
/// on add/remove, not on a bound item's own property mutations.
/// </summary>
public partial class AccountStatusRow : ObservableObject
{
    public string Phone { get; init; } = "";

    [ObservableProperty]
    private string status = "";

    [ObservableProperty]
    private string detail = "";
}

/// <summary>Snapshot from the most recent AccountsDiscoveredEvent -- replaced wholesale
/// (not mutated in place), so a plain record is enough, no ObservableObject needed.</summary>
public sealed record AccountDiscoverySummary(
    int LoadedCount, IReadOnlyList<string> LoadedPhones, int FailedCount, IReadOnlyList<string> FailedReasons);
