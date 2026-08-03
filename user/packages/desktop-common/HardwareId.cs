using System.Management;
using System.Security.Cryptography;
using System.Text;

namespace TgPoolLauncher.Shared;

/// <summary>
/// A stable per-machine fingerprint used to bind a license key to one
/// device (see license_server: activation is rejected once a key is bound
/// to a different hwid hash). Combines several BIOS/board-level identifiers
/// (SMBIOS product UUID, motherboard serial, CPU id) rather than trusting
/// any single one -- all three survive an OS reinstall (unlike a disk
/// serial, deliberately not used here), so a customer re-installing
/// Windows on the same PC doesn't burn their activation, but spoofing the
/// fingerprint now means faking every source consistently, not just one
/// WMI value.
/// </summary>
public static class HardwareId
{
    private static string? _cached;

    /// <summary>Computes (and caches for the process lifetime) a SHA-256 hex fingerprint.</summary>
    public static string Get()
    {
        if (_cached is not null)
            return _cached;

        var components = new[] { ReadMachineUuid(), ReadBaseBoardSerial(), ReadProcessorId() }
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .ToArray();

        // WMI locked down or every source came back empty/placeholder (rare -- some
        // sandboxed/virtualized environments) -- machine name is a weak last resort,
        // same as before this fingerprint was made composite.
        var raw = components.Length > 0 ? string.Join("|", components) : Environment.MachineName;

        _cached = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(raw)));
        return _cached;
    }

    private static string? ReadMachineUuid()
    {
        var value = QuerySingleProperty("SELECT UUID FROM Win32_ComputerSystemProduct", "UUID");
        // Some BIOS/hypervisors ship an unset placeholder instead of a real UUID.
        return IsPlaceholder(value, "00000000-0000-0000-0000-000000000000", "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF")
            ? null
            : value;
    }

    private static string? ReadBaseBoardSerial()
    {
        var value = QuerySingleProperty("SELECT SerialNumber FROM Win32_BaseBoard", "SerialNumber");
        // Common on generic/whitebox boards: the OEM never filled this field in.
        return IsPlaceholder(value, "To be filled by O.E.M.", "Default string", "None", "System Serial Number")
            ? null
            : value;
    }

    private static string? ReadProcessorId()
    {
        return QuerySingleProperty("SELECT ProcessorId FROM Win32_Processor", "ProcessorId");
    }

    private static bool IsPlaceholder(string? value, params string[] knownPlaceholders) =>
        value is not null && knownPlaceholders.Any(p => string.Equals(p, value, StringComparison.OrdinalIgnoreCase));

    /// <summary>
    /// WMI is occasionally unavailable (locked-down group policy, some sandboxed/virtualized
    /// environments) -- ManagementException is the one realistic failure mode here, so it's
    /// the only thing caught; the caller falls back to the next source.
    /// </summary>
    private static string? QuerySingleProperty(string query, string property)
    {
        try
        {
            using var searcher = new ManagementObjectSearcher(query);
            foreach (ManagementBaseObject item in searcher.Get())
            {
                var value = item[property]?.ToString();
                if (!string.IsNullOrWhiteSpace(value))
                    return value.Trim();
            }
        }
        catch (ManagementException)
        {
            // fall through to the next source
        }
        return null;
    }
}
