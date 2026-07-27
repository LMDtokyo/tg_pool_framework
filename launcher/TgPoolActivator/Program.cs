using System.Diagnostics;
using System.Reflection;
using System.Text;
using TgPoolLauncher.Shared;

Console.OutputEncoding = Encoding.UTF8;
Console.Title = "Telegram Andromeda — Activator";

var dataDir = ResolveDataDir(args);
var licenseServerUrl = Environment.GetEnvironmentVariable("LICENSE_SERVER_URL") ?? "http://127.0.0.1:8100";

PrintLogo();

using var client = new LicenseActivationClient(licenseServerUrl);

var installedVersion = ResolveInstalledVersion();
var latestVersion = await client.TryGetLatestVersionAsync();
PrintVersions(installedVersion, latestVersion);

var hwid = HardwareId.Get();
var cached = LicenseCacheFile.TryLoad(dataDir);

if (LicenseCacheFile.IsLocallyValid(cached) && cached!.Hwid == hwid)
{
    Console.ForegroundColor = ConsoleColor.Green;
    Console.WriteLine(
        $"  Лицензия уже активна. Тариф: {cached.Tier}, действует до {cached.ExpiresAt:yyyy-MM-dd HH:mm} UTC.");
    Console.ResetColor();
    Console.WriteLine();
    Console.Write("  Нажмите Enter чтобы продолжить, или введите новый ключ, чтобы сменить: ");
    var choice = Console.ReadLine()?.Trim();
    if (string.IsNullOrWhiteSpace(choice))
        return 0;

    return await ActivateLoopAsync(client, dataDir, hwid, choice) ? 0 : 1;
}

return await ActivateLoopAsync(client, dataDir, hwid, initialKey: null) ? 0 : 1;

static async Task<bool> ActivateLoopAsync(
    LicenseActivationClient client, string dataDir, string hwid, string? initialKey)
{
    var attempt = initialKey;
    while (true)
    {
        if (attempt is null)
        {
            Console.Write("  Введите ключ лицензии (пусто — выход): ");
            attempt = Console.ReadLine()?.Trim();
        }

        if (string.IsNullOrWhiteSpace(attempt))
        {
            Console.WriteLine("  Отменено.");
            return false;
        }

        try
        {
            var result = await client.ActivateAsync(attempt, hwid);
            LicenseCacheFile.Save(dataDir, new CachedLicense
            {
                LicenseKey = attempt,
                Hwid = hwid,
                Tier = result.Tier,
                ExpiresAt = result.ExpiresAt,
            });

            Console.WriteLine();
            Console.ForegroundColor = ConsoleColor.Green;
            Console.WriteLine(
                $"  Готово! Тариф «{result.Tier}» активирован, действует до {result.ExpiresAt:yyyy-MM-dd HH:mm} UTC.");
            Console.ResetColor();
            return true;
        }
        catch (LicenseActivationException ex)
        {
            Console.WriteLine();
            Console.ForegroundColor = ConsoleColor.Red;
            Console.WriteLine($"  Ошибка: {DescribeFailure(ex.Reason)}");
            Console.ResetColor();
            Console.WriteLine();
            attempt = null;
        }
    }
}

static string DescribeFailure(LicenseFailureReason reason) => reason switch
{
    LicenseFailureReason.NotFound => "ключ не найден — проверьте правильность ввода.",
    LicenseFailureReason.Revoked => "этот ключ отозван.",
    LicenseFailureReason.Expired => "срок действия этого ключа истёк.",
    LicenseFailureReason.DeviceMismatch => "этот ключ уже активирован на другом устройстве.",
    LicenseFailureReason.ServerUnavailable =>
        "не удалось связаться с сервером лицензий. Проверьте интернет-соединение и попробуйте снова.",
    _ => "неизвестная ошибка.",
};

static string ResolveInstalledVersion()
{
    var launcherPath = Path.Combine(AppContext.BaseDirectory, "TgPoolLauncher.exe");
    if (File.Exists(launcherPath))
    {
        var info = FileVersionInfo.GetVersionInfo(launcherPath);
        if (!string.IsNullOrWhiteSpace(info.ProductVersion))
            return info.ProductVersion;
    }
    return Assembly.GetExecutingAssembly().GetName().Version?.ToString() ?? "unknown";
}

/// <summary>
/// --data-dir wins when the WPF app spawns us. Standalone runs (a customer
/// double-clicking the activator on its own) fall back to the same
/// repo-root heuristic App.xaml.cs uses for a dev checkout, or Data\ next
/// to this exe in a real install.
/// </summary>
static string ResolveDataDir(string[] args)
{
    for (var i = 0; i < args.Length - 1; i++)
    {
        if (args[i] == "--data-dir")
            return args[i + 1];
    }

    var dir = new DirectoryInfo(AppContext.BaseDirectory);
    while (dir is not null && !File.Exists(Path.Combine(dir.FullName, "requirements.txt")))
        dir = dir.Parent;
    var root = dir?.FullName ?? AppContext.BaseDirectory;
    return Path.Combine(root, "Data");
}

static void PrintVersions(string installed, string? latest)
{
    Console.ForegroundColor = ConsoleColor.DarkGray;
    Console.WriteLine($"  Установлена версия : {installed}");
    Console.WriteLine(latest is null
        ? "  Актуальная версия  : не удалось проверить (нет соединения с сервером)"
        : $"  Актуальная версия  : {latest}" + (latest != installed ? "  (доступно обновление)" : ""));
    Console.ResetColor();
    Console.WriteLine();
}

static void PrintLogo()
{
    Console.ForegroundColor = ConsoleColor.Cyan;
    Console.WriteLine();
    Console.WriteLine(@"    _              _                            _       ");
    Console.WriteLine(@"   / \   _ __   __| |_ __ ___  _ __ ___   ___  __| | __ _ ");
    Console.WriteLine(@"  / _ \ | '_ \ / _` | '__/ _ \| '_ ` _ \ / _ \/ _` |/ _` |");
    Console.WriteLine(@" / ___ \| | | | (_| | | | (_) | | | | | |  __/ (_| | (_| |");
    Console.WriteLine(@"/_/   \_\_| |_|\__,_|_|  \___/|_| |_| |_|\___|\__,_|\__,_|");
    Console.ResetColor();
    Console.WriteLine();
    Console.WriteLine("  Telegram Andromeda — активация лицензии");
    Console.WriteLine("  ────────────────────────────────────────");
    Console.WriteLine();
}
