using System.Net.Http.Json;
using System.Text.Json.Serialization;

namespace TgPoolLauncher.Shared;

public sealed record LatestRelease(string LatestVersion, string Notes, string DownloadUrl);

public enum LicenseFailureReason
{
    NotFound,
    Revoked,
    Expired,
    DeviceMismatch,
    ServerUnavailable,
}

public sealed class LicenseActivationException(LicenseFailureReason reason, string message) : Exception(message)
{
    public LicenseFailureReason Reason { get; } = reason;
}

public sealed record LicenseActivationResult(string Tier, DateTimeOffset ActivatedAt, DateTimeOffset ExpiresAt);

/// <summary>
/// Talks to the versioned public central license API,
/// not to the customer's local backend -- used by TgPoolActivator, which
/// runs standalone, separately from the main WPF app and its Python
/// backend. Mirrors the generated public license contract.
/// </summary>
public sealed class LicenseActivationClient : IDisposable
{
    private readonly HttpClient _http;

    public LicenseActivationClient(string licenseServerUrl, TimeSpan? timeout = null)
    {
        // HttpClient.BaseAddress + a relative URI combine per RFC 3986: a leading
        // slash on the relative part resets to the host root, discarding any path
        // on BaseAddress entirely (e.g. base "https://host/license-api" + relative
        // "/version" resolves to "https://host/version", NOT ".../license-api/version").
        // Forcing a trailing slash here, paired with no leading slash on every call
        // below, is the only combination that actually appends instead of replacing.
        _http = new HttpClient
        {
            BaseAddress = new Uri(licenseServerUrl.TrimEnd('/') + "/"),
            Timeout = timeout ?? TimeSpan.FromSeconds(15),
        };
    }

    public async Task<LicenseActivationResult> ActivateAsync(
        string licenseKey, string hwid, CancellationToken ct = default)
    {
        HttpResponseMessage response;
        try
        {
            response = await _http.PostAsJsonAsync(
                "license/activate", new ActivateRequestBody(licenseKey, hwid), ct);
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException)
        {
            throw new LicenseActivationException(LicenseFailureReason.ServerUnavailable, ex.Message);
        }

        if (response.IsSuccessStatusCode)
        {
            var body = await response.Content.ReadFromJsonAsync<ActivateResponseBody>(cancellationToken: ct);
            if (body is null)
                throw new LicenseActivationException(LicenseFailureReason.ServerUnavailable, "Empty response body");
            return new LicenseActivationResult(body.Tier, body.ActivatedAt, body.ExpiresAt);
        }

        var (reason, message) = await ParseErrorAsync(response, ct);
        throw new LicenseActivationException(reason, message);
    }

    /// <summary>Best-effort -- a version-check failure must never block activation.</summary>
    public async Task<string?> TryGetLatestVersionAsync(CancellationToken ct = default)
    {
        try
        {
            var body = await _http.GetFromJsonAsync<VersionResponseBody>("version", ct);
            return body?.LatestVersion;
        }
        catch (Exception)
        {
            return null;
        }
    }

    /// <summary>
    /// Same /version endpoint as <see cref="TryGetLatestVersionAsync"/>, but for the
    /// main WPF app's Dashboard update card, which also needs the notes and download
    /// link. Best-effort, same as above -- a failed check must never block the app.
    /// </summary>
    public async Task<LatestRelease?> TryGetLatestReleaseAsync(CancellationToken ct = default)
    {
        try
        {
            var body = await _http.GetFromJsonAsync<VersionResponseBody>("version", ct);
            if (body is null || string.IsNullOrWhiteSpace(body.LatestVersion))
                return null;
            return new LatestRelease(body.LatestVersion, body.Notes, body.DownloadUrl);
        }
        catch (Exception)
        {
            return null;
        }
    }

    /// <summary>Streams the installer to <paramref name="destPath"/>, reporting progress by byte count.</summary>
    public async Task DownloadInstallerAsync(
        string downloadUrl, string destPath, IProgress<double> progress, CancellationToken ct = default)
    {
        using var response = await _http.GetAsync(downloadUrl, HttpCompletionOption.ResponseHeadersRead, ct);
        response.EnsureSuccessStatusCode();
        var total = response.Content.Headers.ContentLength ?? -1;
        await using var source = await response.Content.ReadAsStreamAsync(ct);
        await using var dest = File.Create(destPath);
        var buffer = new byte[81920];
        long readTotal = 0;
        int read;
        while ((read = await source.ReadAsync(buffer, ct)) > 0)
        {
            await dest.WriteAsync(buffer.AsMemory(0, read), ct);
            readTotal += read;
            if (total > 0)
                progress.Report((double)readTotal / total);
        }
    }

    private static async Task<(LicenseFailureReason Reason, string Message)> ParseErrorAsync(
        HttpResponseMessage response, CancellationToken ct)
    {
        try
        {
            var body = await response.Content.ReadFromJsonAsync<ErrorResponseBody>(cancellationToken: ct);
            var reason = body?.Detail?.Reason switch
            {
                "not_found" => LicenseFailureReason.NotFound,
                "revoked" => LicenseFailureReason.Revoked,
                "expired" => LicenseFailureReason.Expired,
                "device_mismatch" => LicenseFailureReason.DeviceMismatch,
                _ => LicenseFailureReason.ServerUnavailable,
            };
            return (reason, body?.Detail?.Message ?? $"HTTP {(int)response.StatusCode}");
        }
        catch (Exception)
        {
            return (LicenseFailureReason.ServerUnavailable, $"HTTP {(int)response.StatusCode}");
        }
    }

    public void Dispose() => _http.Dispose();

    private sealed class ActivateRequestBody(string licenseKey, string hwid)
    {
        [JsonPropertyName("license_key")]
        public string LicenseKey { get; } = licenseKey;

        [JsonPropertyName("hwid")]
        public string Hwid { get; } = hwid;
    }

    private sealed class ActivateResponseBody
    {
        [JsonPropertyName("tier")]
        public string Tier { get; set; } = "";

        [JsonPropertyName("activated_at")]
        public DateTimeOffset ActivatedAt { get; set; }

        [JsonPropertyName("expires_at")]
        public DateTimeOffset ExpiresAt { get; set; }
    }

    private sealed class VersionResponseBody
    {
        [JsonPropertyName("latest_version")]
        public string LatestVersion { get; set; } = "";

        [JsonPropertyName("notes")]
        public string Notes { get; set; } = "";

        [JsonPropertyName("download_url")]
        public string DownloadUrl { get; set; } = "";
    }

    private sealed class ErrorResponseBody
    {
        [JsonPropertyName("detail")]
        public ErrorDetail? Detail { get; set; }
    }

    private sealed class ErrorDetail
    {
        [JsonPropertyName("reason")]
        public string? Reason { get; set; }

        [JsonPropertyName("message")]
        public string? Message { get; set; }
    }
}
