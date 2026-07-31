using System.Diagnostics;
using System.ComponentModel;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Security.Cryptography;

namespace TgPoolLauncher.Services;

/// <summary>
/// Launches the Python control API (src/api/app.py, via uvicorn) as a child
/// process and polls /health until it's ready. Owns the process's lifetime --
/// terminated on DisposeAsync (called from App.xaml.cs's OnExit).
/// </summary>
public sealed class BackendProcessManager : IAsyncDisposable
{
    private const long MaxLogFileBytes = 5 * 1024 * 1024;
    private readonly string _pythonExecutable;
    private readonly string _repoRoot;
    private readonly int _port;
    private readonly IReadOnlyDictionary<string, string>? _environmentVariables;
    private Process? _process;

    public Uri BaseUri { get; }
    public string? LastStartupError { get; private set; }

    /// <summary>
    /// Random per-launch secret shared only with this specific child process
    /// (via the LOCAL_API_TOKEN env var, see src/api/local_auth.py) -- lets
    /// the backend tell "the launcher that spawned me" apart from any other
    /// local process that might otherwise reach its loopback port.
    /// </summary>
    public string LocalApiToken { get; } = Convert.ToBase64String(RandomNumberGenerator.GetBytes(32));

    public BackendProcessManager(
        string repoRoot,
        string pythonExecutable = "python",
        int port = 0,
        IReadOnlyDictionary<string, string>? environmentVariables = null)
    {
        _repoRoot = repoRoot;
        _pythonExecutable = pythonExecutable;
        _port = port > 0 ? port : FindAvailableLoopbackPort();
        _environmentVariables = environmentVariables;
        BaseUri = new Uri($"http://127.0.0.1:{_port}");
    }

    private static int FindAvailableLoopbackPort()
    {
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        try
        {
            return ((IPEndPoint)listener.LocalEndpoint).Port;
        }
        finally
        {
            listener.Stop();
        }
    }

    public async Task<bool> StartAndWaitReadyAsync(TimeSpan timeout, CancellationToken ct = default)
    {
        LastStartupError = null;
        var psi = new ProcessStartInfo
        {
            FileName = _pythonExecutable,
            Arguments = $"-m uvicorn src.api.app:app --host 127.0.0.1 --port {_port} --no-access-log",
            WorkingDirectory = _repoRoot,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };

        if (_environmentVariables is not null)
            foreach (var (key, value) in _environmentVariables)
                psi.EnvironmentVariables[key] = value;
        psi.EnvironmentVariables["LOCAL_API_TOKEN"] = LocalApiToken;

        try
        {
            _process = Process.Start(psi);
        }
        catch (Win32Exception exc)
        {
            LastStartupError = $"Could not launch Python executable '{_pythonExecutable}': {exc.Message}";
            return false;
        }
        catch (InvalidOperationException exc)
        {
            LastStartupError = $"Could not launch Python executable '{_pythonExecutable}': {exc.Message}";
            return false;
        }

        if (_process is null)
        {
            LastStartupError = $"Could not launch Python executable '{_pythonExecutable}'.";
            return false;
        }

        // RedirectStandardOutput/Error requires the pipes to be drained continuously --
        // otherwise the OS pipe buffer fills once the backend logs enough, and uvicorn
        // blocks trying to write to a full pipe. Persisting to Data\Logs also gives us a
        // diagnostic trail for backend-side crashes.
        AttachLogDrain(_process, _environmentVariables);

        using var http = new HttpClient { BaseAddress = BaseUri, Timeout = TimeSpan.FromSeconds(2) };
        var deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < deadline)
        {
            if (_process.HasExited)
            {
                LastStartupError = $"Backend process exited early with code {_process.ExitCode}. Check Data\\Logs\\backend-stderr.log for details.";
                return false;
            }
            try
            {
                var resp = await http.GetAsync("/health", ct);
                if (resp.IsSuccessStatusCode)
                    return true;
            }
            catch (HttpRequestException)
            {
                // backend not accepting connections yet
            }
            catch (TaskCanceledException)
            {
                // health check request itself timed out -- keep polling
            }
            await Task.Delay(300, ct);
        }
        LastStartupError = $"Backend did not become ready within {timeout.TotalSeconds:0} seconds. Check Data\\Logs\\backend-stderr.log for details.";
        return false;
    }

    /// <summary>
    /// Continuously drains stdout/stderr so the child process never blocks on a
    /// full pipe. Persists each stream to Data\Logs\backend-std{out,err}.log
    /// (truncated at the start of each run) when a LOG_DIR was provided;
    /// otherwise just drains without writing anywhere.
    /// </summary>
    private static void AttachLogDrain(Process process, IReadOnlyDictionary<string, string>? environmentVariables)
    {
        string? logDir = null;
        environmentVariables?.TryGetValue("LOG_DIR", out logDir);

        string? stdoutPath = null;
        string? stderrPath = null;
        if (!string.IsNullOrEmpty(logDir))
        {
            stdoutPath = Path.Combine(logDir, "backend-stdout.log");
            stderrPath = Path.Combine(logDir, "backend-stderr.log");
            File.WriteAllText(stdoutPath, "");
            File.WriteAllText(stderrPath, "");
        }

        process.OutputDataReceived += (_, args) =>
        {
            if (args.Data is not null && stdoutPath is not null)
                TryAppendLine(stdoutPath, args.Data);
        };
        process.ErrorDataReceived += (_, args) =>
        {
            if (args.Data is not null && stderrPath is not null)
                TryAppendLine(stderrPath, args.Data);
        };
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
    }

    private static void TryAppendLine(string path, string line)
    {
        try
        {
            var file = new FileInfo(path);
            if (file.Exists && file.Length >= MaxLogFileBytes)
                File.WriteAllText(path, "");
            File.AppendAllText(path, line + Environment.NewLine);
        }
        catch (IOException)
        {
            // best-effort logging -- a transient file-lock must not crash the backend watcher
        }
    }

    public ValueTask DisposeAsync()
    {
        if (_process is { HasExited: false })
        {
            try
            {
                _process.Kill(entireProcessTree: true);
            }
            catch (InvalidOperationException)
            {
                // already exited between the check and Kill()
            }
        }
        _process?.Dispose();
        return ValueTask.CompletedTask;
    }
}
