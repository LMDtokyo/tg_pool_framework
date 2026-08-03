using System.ComponentModel;
using System.IO;
using System.Net.Http;
using System.Text.RegularExpressions;
using System.Windows;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using TgPoolLauncher.Services;
using TgPoolLauncher.ViewModels;
using TgPoolLauncher.Views;
using Forms = System.Windows.Forms;

namespace TgPoolLauncher;

/// <summary>
/// Composition root: builds a Generic Host for DI (per Microsoft's documented
/// WPF + Generic Host pattern), starts the Python backend as a child process,
/// waits for /health, then constructs and shows MainWindow via DI.
/// </summary>
public partial class App : System.Windows.Application
{
    private IHost? _host;
    private Forms.NotifyIcon? _trayIcon;
    private bool _exitRequested;

    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        // Default ShutdownMode is OnLastWindowClose: once the splash window closes itself
        // (after its ~5s animation), WPF sees zero open windows -- if MainWindow isn't up
        // yet (still awaiting backend readiness), the whole app quietly exits right there,
        // with no exception and no error to show for it. Explicit mode holds it open until
        // MainWindow.Show() below re-enables normal close-to-exit behavior.
        ShutdownMode = ShutdownMode.OnExplicitShutdown;

        DispatcherUnhandledException += (_, args) =>
            WriteCrashLog("DispatcherUnhandledException", args.Exception.ToString());
        AppDomain.CurrentDomain.UnhandledException += (_, args) =>
            WriteCrashLog("AppDomain.UnhandledException", args.ExceptionObject?.ToString() ?? "null");

        var localAgentRoot = ResolveLocalAgentRoot();
        AppPaths.Initialize(localAgentRoot);

        // License gate runs before anything else: a console window (TgPoolActivator.exe,
        // a separate process from this app) prompts for the key when there's no locally
        // valid cached activation. No point starting the Python backend for a customer
        // who isn't licensed.
        if (!LicenseGateway.HasLocallyValidLicense(AppPaths.Data))
        {
            var activated = await LicenseGateway.RunActivatorAsync(localAgentRoot, AppPaths.Data);
            if (!activated || !LicenseGateway.HasLocallyValidLicense(AppPaths.Data))
            {
                MessageBox.Show(
                    Localization.LocalizationService.Instance["App.LicenseActivationFailedMessage"],
                    "TgPoolLauncher", MessageBoxButton.OK, MessageBoxImage.Error);
                Shutdown(-1);
                return;
            }
        }

        _host = Host.CreateDefaultBuilder()
            .ConfigureServices((_, services) =>
            {
                services.AddSingleton(new BackendProcessManager(
                    localAgentRoot,
                    pythonExecutable: ResolvePythonExecutable(localAgentRoot),
                    environmentVariables: AppPaths.BackendEnvironmentVariables));
                services.AddHttpClient<BackendClient>((sp, http) =>
                {
                    var processManager = sp.GetRequiredService<BackendProcessManager>();
                    http.BaseAddress = processManager.BaseUri;
                    http.DefaultRequestHeaders.Add("X-Local-Token", processManager.LocalApiToken);
                });
                services.AddSingleton(sp =>
                {
                    var processManager = sp.GetRequiredService<BackendProcessManager>();
                    return new EventStreamClient(processManager.BaseUri, processManager.LocalApiToken);
                });
                services.AddHttpClient<RecommendedToolsService>();

                services.AddSingleton<DashboardViewModel>();
                services.AddSingleton<AccountsViewModel>();
                services.AddSingleton<ProxyCheckViewModel>();
                services.AddSingleton<ProxyPoolCheckerViewModel>();
                services.AddSingleton<TdataConvertViewModel>();
                services.AddSingleton<ParsingViewModel>();
                services.AddSingleton<ScheduledCampaignsViewModel>();
                services.AddSingleton<EngagementViewModel>();
                services.AddSingleton<StoriesViewModel>();
                services.AddSingleton<SessionConvertViewModel>();
                services.AddSingleton<JsonGeneratorViewModel>();
                services.AddSingleton<TextRandomizerViewModel>();
                services.AddSingleton<AutoRegisterNavigationViewModel>();
                services.AddSingleton<HeroSmsViewModel>();
                services.AddSingleton<SmsPoolViewModel>();
                services.AddSingleton<GrizzlySmsViewModel>();
                services.AddSingleton<DatamollViewModel>();
                services.AddSingleton<ManualViewModel>();
                services.AddSingleton<LicenseStatusViewModel>();

                services.AddSingleton<DashboardView>();
                services.AddSingleton<AccountsView>();
                services.AddSingleton<ProxyCheckView>();
                services.AddSingleton<ProxyPoolCheckerView>();
                services.AddSingleton<TdataConvertView>();
                services.AddSingleton<ParsingView>();
                services.AddSingleton<SessionConvertView>();
                services.AddSingleton<JsonGeneratorView>();
                services.AddSingleton<TextRandomizerView>();
                services.AddSingleton<UniversalActivateView>();
                services.AddSingleton<HeroSmsView>();
                services.AddSingleton<SmsPoolView>();
                services.AddSingleton<GrizzlySmsView>();
                services.AddSingleton<DatamollView>();
                services.AddSingleton<InviteByNumberView>();
                services.AddSingleton<SendingSmsByIdView>();
                services.AddSingleton<SendByNumbersView>();
                services.AddSingleton<NumberCheckerView>();
                services.AddSingleton<ScheduledCampaignsView>();
                services.AddSingleton<EngagementView>();
                services.AddSingleton<StoriesView>();
                services.AddSingleton<AutoRegisterHostView>();
                services.AddSingleton<ManualView>();
                services.AddSingleton<MainWindow>();
            })
            .Build();

        await _host.StartAsync();

        // Splash runs its fixed ~5s fade-in/hold/fade-out concurrently with backend startup,
        // so a fast backend doesn't shorten the splash and a slow one doesn't add its full
        // startup time on top of it -- total wait is max(splash, backend), not their sum.
        var splash = new SplashWindow();
        var splashTask = splash.RunAsync();

        var processManager = _host.Services.GetRequiredService<BackendProcessManager>();
        var ready = await processManager.StartAndWaitReadyAsync(TimeSpan.FromSeconds(20));
        await splashTask;

        if (!ready)
        {
            var message = Localization.LocalizationService.Instance["App.BackendFailedMessage"];
            if (!string.IsNullOrWhiteSpace(processManager.LastStartupError))
                message += "\n\n" + processManager.LastStartupError;

            MessageBox.Show(
                message,
                "TgPoolLauncher", MessageBoxButton.OK, MessageBoxImage.Error);
            Shutdown(-1);
            return;
        }

        // Forward the console activator's cached key+hwid to the local backend, which now
        // owns its own periodic re-validation against the license server (tg_pool/licensing) --
        // this call just seeds that state, it doesn't gate this WPF process itself. The
        // returned status (tier + expiry) also feeds the sidebar's subscription countdown.
        var licenseStatus = await LicenseGateway.SyncBackendAsync(_host.Services.GetRequiredService<BackendClient>(), AppPaths.Data);
        _host.Services.GetRequiredService<LicenseStatusViewModel>().SetStatus(licenseStatus);

        // Same reasoning: the backend process's env vars are fixed at launch, so whatever
        // default api_id/api_hash the operator saved last session must be re-sent here.
        await SyncDefaultCredentialsAsync(_host.Services.GetRequiredService<BackendClient>());

        _host.Services.GetRequiredService<EventStreamClient>().Start();

        var mainWindow = _host.Services.GetRequiredService<MainWindow>();
        MainWindow = mainWindow;
        mainWindow.Closing += MainWindowOnClosing;
        InitializeTrayIcon();
        mainWindow.Show();
        mainWindow.FadeIn();
    }

    /// <summary>No-op if nothing was ever saved (Accounts tab, "default api_id/api_hash" field).</summary>
    private static async Task SyncDefaultCredentialsAsync(BackendClient backend)
    {
        var cached = DefaultCredentialsCacheFile.TryLoad(AppPaths.Data);
        if (cached is null || cached.ApiId <= 0 || string.IsNullOrEmpty(cached.ApiHash))
            return;
        try
        {
            await backend.SetDefaultCredentialsAsync(cached.ApiId, cached.ApiHash);
        }
        catch (HttpRequestException)
        {
            // best-effort -- a stale/unreachable backend must not block startup
        }
    }

    private void InitializeTrayIcon()
    {
        var menu = new Forms.ContextMenuStrip();
        menu.Items.Add("Show/Hide Window", null, (_, _) => ToggleMainWindow());
        menu.Items.Add(new Forms.ToolStripSeparator());
        menu.Items.Add("Exit", null, (_, _) => ExitApplication());

        _trayIcon = new Forms.NotifyIcon
        {
            Icon = System.Drawing.SystemIcons.Application,
            Text = "TgPoolLauncher",
            ContextMenuStrip = menu,
            Visible = true,
        };
        _trayIcon.DoubleClick += (_, _) => ShowMainWindow();
    }

    private void MainWindowOnClosing(object? sender, CancelEventArgs e)
    {
        if (_exitRequested)
            return;

        e.Cancel = true;
        MainWindow?.Hide();
    }

    private void ToggleMainWindow()
    {
        Dispatcher.Invoke(() =>
        {
            if (MainWindow?.IsVisible == true)
                MainWindow.Hide();
            else
                ShowMainWindow();
        });
    }

    private void ShowMainWindow()
    {
        Dispatcher.Invoke(() =>
        {
            if (MainWindow is null)
                return;
            MainWindow.Show();
            if (MainWindow.WindowState == WindowState.Minimized)
                MainWindow.WindowState = WindowState.Normal;
            MainWindow.Activate();
        });
    }

    private void ExitApplication()
    {
        Dispatcher.Invoke(() =>
        {
            _exitRequested = true;
            MainWindow?.Close();
            Shutdown();
        });
    }

    protected override async void OnExit(ExitEventArgs e)
    {
        if (_trayIcon is not null)
        {
            _trayIcon.Visible = false;
            _trayIcon.ContextMenuStrip?.Dispose();
            _trayIcon.Dispose();
            _trayIcon = null;
        }
        if (_host is not null)
        {
            var eventStream = _host.Services.GetRequiredService<EventStreamClient>();
            var processManager = _host.Services.GetRequiredService<BackendProcessManager>();
            await eventStream.DisposeAsync();
            await processManager.DisposeAsync();
            await _host.StopAsync();
            _host.Dispose();
        }
        base.OnExit(e);
    }

    /// <summary>
    /// Resolves the independently deployable local-agent root. Installed builds keep
    /// requirements.txt beside the executable; development builds find it under
    /// user/services/local-agent from the user project root.
    /// </summary>
    private static string ResolveLocalAgentRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            if (File.Exists(Path.Combine(dir.FullName, "requirements.txt")) &&
                Directory.Exists(Path.Combine(dir.FullName, "tg_pool")))
                return dir.FullName;

            var nestedAgent = Path.Combine(dir.FullName, "services", "local-agent");
            if (File.Exists(Path.Combine(nestedAgent, "requirements.txt")) &&
                Directory.Exists(Path.Combine(nestedAgent, "tg_pool")))
                return nestedAgent;

            dir = dir.Parent;
        }
        return AppContext.BaseDirectory;
    }

    /// <summary>
    /// Development checkouts usually keep dependencies in .venv. Installed builds
    /// fall back to Python from PATH, after the installer has prepared it.
    /// </summary>
    private static string ResolvePythonExecutable(string repoRoot)
    {
        var venvPython = Path.Combine(repoRoot, ".venv", "Scripts", "python.exe");
        return File.Exists(venvPython) ? venvPython : "python";
    }

    private static readonly Regex ApiHashPattern = new(@"\b[0-9a-fA-F]{32}\b", RegexOptions.Compiled);
    private static readonly Regex CredentialUrlPattern = new(@"://[^/\s:@]+:[^/\s:@]+@", RegexOptions.Compiled);

    /// <summary>
    /// Persists a crash report under Data\Crashes -- falls back to the base
    /// directory if a crash happens before AppPaths.Initialize() has run.
    /// Best-effort: a failure here must never mask the original crash.
    /// </summary>
    private static void WriteCrashLog(string kind, string details)
    {
        try
        {
            var dir = string.IsNullOrEmpty(AppPaths.Crashes) ? AppContext.BaseDirectory : AppPaths.Crashes;
            var path = Path.Combine(dir, $"crash-{DateTime.Now:yyyyMMdd-HHmmss}.log");
            File.WriteAllText(path, $"{kind}\n{ScrubSecrets(details)}");
        }
        catch
        {
            // best-effort -- swallow so the crash handler itself can't throw
        }
    }

    /// <summary>
    /// Redacts secret-shaped substrings (api_hash-style hex, credential URLs) that
    /// could theoretically end up embedded in an exception's message or Data before
    /// this best-effort dump lands on disk. Defense in depth, not a guarantee --
    /// nothing in this app currently puts a raw secret into an exception.
    /// </summary>
    private static string ScrubSecrets(string text)
    {
        text = ApiHashPattern.Replace(text, "[redacted]");
        text = CredentialUrlPattern.Replace(text, "://[redacted]@");
        return text;
    }
}
