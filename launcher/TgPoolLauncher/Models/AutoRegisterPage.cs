using System.Windows.Controls;

namespace TgPoolLauncher.Models;

/// <summary>
/// Describes one page available inside the Auto Register section.
/// Adding a provider only requires registering another descriptor.
/// </summary>
public sealed record AutoRegisterPage(string Id, string DisplayName, UserControl Content, string? GroupName = null);
