using System.IO;
using System.Net.WebSockets;
using System.Text.Json;
using TgPoolLauncher.Models;

namespace TgPoolLauncher.Services;

/// <summary>
/// Wraps ClientWebSocket for the /ws/events feed (tg_pool/api/events.py). Runs a
/// background receive loop with reconnect-with-backoff; EventReceived fires
/// from that background task, NOT the UI thread -- subscribers must marshal
/// back via the Dispatcher before touching bound WPF state.
/// </summary>
public sealed class EventStreamClient : IAsyncDisposable
{
    private readonly Uri _uri;
    private readonly string? _localApiToken;
    private CancellationTokenSource? _cts;
    private Task? _runTask;

    public event Action<EventEnvelope>? EventReceived;
    public event Action<bool>? ConnectionStateChanged;

    public EventStreamClient(Uri backendBaseUri, string? localApiToken = null)
    {
        var builder = new UriBuilder(backendBaseUri)
        {
            Scheme = backendBaseUri.Scheme == "https" ? "wss" : "ws",
            Path = "/ws/events",
        };
        _uri = builder.Uri;
        _localApiToken = localApiToken;
    }

    public void Start()
    {
        if (_runTask is not null)
            return;
        _cts = new CancellationTokenSource();
        _runTask = RunAsync(_cts.Token);
    }

    public async ValueTask DisposeAsync()
    {
        _cts?.Cancel();
        if (_runTask is not null)
        {
            try
            {
                await _runTask;
            }
            catch (OperationCanceledException)
            {
                // expected on shutdown
            }
        }
        _cts?.Dispose();
    }

    private async Task RunAsync(CancellationToken ct)
    {
        var backoff = TimeSpan.FromSeconds(1);
        while (!ct.IsCancellationRequested)
        {
            using var socket = new ClientWebSocket();
            if (!string.IsNullOrEmpty(_localApiToken))
                socket.Options.SetRequestHeader("X-Local-Token", _localApiToken);
            try
            {
                await socket.ConnectAsync(_uri, ct);
                ConnectionStateChanged?.Invoke(true);
                backoff = TimeSpan.FromSeconds(1);
                await ReceiveLoopAsync(socket, ct);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception)
            {
                // Connection dropped or failed to establish -- fall through to reconnect.
            }
            finally
            {
                ConnectionStateChanged?.Invoke(false);
            }

            if (ct.IsCancellationRequested)
                break;
            try
            {
                await Task.Delay(backoff, ct);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            backoff = TimeSpan.FromSeconds(Math.Min(backoff.TotalSeconds * 2, 30));
        }
    }

    private async Task ReceiveLoopAsync(ClientWebSocket socket, CancellationToken ct)
    {
        var buffer = new byte[8192];
        while (socket.State == WebSocketState.Open && !ct.IsCancellationRequested)
        {
            using var stream = new MemoryStream();
            WebSocketReceiveResult result;
            do
            {
                result = await socket.ReceiveAsync(buffer, ct);
                if (result.MessageType == WebSocketMessageType.Close)
                    return;
                stream.Write(buffer, 0, result.Count);
            } while (!result.EndOfMessage);

            stream.Position = 0;
            var envelope = await JsonSerializer.DeserializeAsync<EventEnvelope>(stream, cancellationToken: ct);
            if (envelope is not null)
                EventReceived?.Invoke(envelope);
        }
    }
}
