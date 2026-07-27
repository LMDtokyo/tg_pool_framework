using System.Management;
using System.Security.Cryptography;
using System.Text;

namespace TgPoolLauncher.Shared;

/// <summary>
/// A stable per-machine fingerprint used to bind a license key to one
/// device (see license_server: activation is rejected once a key is bound
/// to a different hwid hash). Sourced from the motherboard/BIOS-level
/// product UUID, which survives an OS reinstall (unlike a disk serial),
/// so a customer re-installing Windows on the same PC doesn't accidentally
/// burn their single-device activation.
/// </summary>
public static class HardwareId
{
    private static string? _cached;

    /// <summary>Computes (and caches for the process lifetime) a SHA-256 hex fingerprint.</summary>
    public static string Get()
    {
        if (_cached is not null)
            return _cached;

        var raw = ReadMachineUuid() ?? ReadBaseBoardSerial() ?? Environment.MachineName;
        _cached = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(raw)));
        return _cached;
    }

    private static string? ReadMachineUuid()
    {
        return QuerySingleProperty("SELECT UUID FROM Win32_ComputerSystemProduct", "UUID");
    }

    private static string? ReadBaseBoardSerial()
    {
        return QuerySingleProperty("SELECT SerialNumber FROM Win32_BaseBoard", "SerialNumber");
    }

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
