using System.IO;

namespace TgPoolLauncher.Services;

/// <summary>
/// Portable-app data layout: everything the framework reads/writes (accounts,
/// spare accounts, tdata sources, converted sessions, tdata exports, proxy
/// lists, parsing exports) lives under a `Data\` folder next to wherever the
/// app is installed -- no admin rights needed, survives reinstall-in-place,
/// easy to move to another PC by copying the install folder.
/// </summary>
public static class AppPaths
{
    public static string Root { get; private set; } = "";
    public static string Data { get; private set; } = "";
    public static string Accounts { get; private set; } = "";
    public static string SpareAccounts { get; private set; } = "";
    public static string Tdata { get; private set; } = "";
    public static string Sessions { get; private set; } = "";
    public static string TdataExports { get; private set; } = "";
    public static string Proxies { get; private set; } = "";
    public static string Exports { get; private set; } = "";
    public static string Logs { get; private set; } = "";
    public static string Crashes { get; private set; } = "";
    public static string Fingerprints { get; private set; } = "";
    public static string JsonGenerator { get; private set; } = "";
    public static string Tools { get; private set; } = "";

    /// <summary>Computes every path and creates each folder if missing. Call once at startup.</summary>
    public static void Initialize(string root)
    {
        Root = root;
        Data = Path.Combine(root, "Data");
        Accounts = Path.Combine(Data, "Accounts");
        SpareAccounts = Path.Combine(Data, "AccountsSpare");
        Tdata = Path.Combine(Data, "Tdata");
        Sessions = Path.Combine(Data, "Sessions");
        TdataExports = Path.Combine(Data, "TdataExports");
        Proxies = Path.Combine(Data, "Proxies");
        Exports = Path.Combine(Data, "Exports");
        Logs = Path.Combine(Data, "Logs");
        Crashes = Path.Combine(Data, "Crashes");
        Fingerprints = Path.Combine(Data, "Fingerprints");
        JsonGenerator = Path.Combine(Data, "JsonGenerator");
        Tools = Path.Combine(Data, "Tools");

        foreach (var dir in new[] { Accounts, SpareAccounts, Tdata, Sessions, TdataExports, Proxies, Exports, Logs, Crashes, Fingerprints, JsonGenerator, Tools })
            Directory.CreateDirectory(dir);
    }

    /// <summary>
    /// Env vars the Python local agent (tg_pool/bootstrap.py) reads at API startup to
    /// discover the primary/spare account pool and tdata sources, and where to
    /// write its log file -- passed to the uvicorn child process so the
    /// managed Data folders are the default without editing .env.
    /// </summary>
    public static IReadOnlyDictionary<string, string> BackendEnvironmentVariables => new Dictionary<string, string>
    {
        ["ACCOUNTS_DIR"] = Accounts,
        ["SPARE_ACCOUNTS_DIR"] = SpareAccounts,
        ["TDATA_ACCOUNTS_DIR"] = Tdata,
        ["SESSION_DIR"] = Sessions,
        ["TELEGRAM_FINGERPRINT_FILE"] = Path.Combine(Fingerprints, "telegram_devices.xlsx"),
        ["LOG_DIR"] = Logs,
        ["ACCOUNT_DATABASE_URL"] = BuildAccountDatabaseUrl(),
        ["PROXY_DATABASE_URL"] = BuildProxyDatabaseUrl(),
    };

    private static string BuildAccountDatabaseUrl()
    {
        var path = Path.Combine(Accounts, "accounts.db").Replace('\\', '/');
        return $"sqlite+aiosqlite:///{path}";
    }

    private static string BuildProxyDatabaseUrl()
    {
        var path = Path.Combine(Proxies, "proxies.db").Replace('\\', '/');
        return $"sqlite+aiosqlite:///{path}";
    }
}
