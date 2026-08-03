import pytest

from tg_pool.proxy.proxy_pool_checker import ProxyPoolAttempt, check_proxy_pool


@pytest.mark.asyncio
async def test_rotating_pool_counts_unique_duplicates_and_errors():
    ips = ["1.1.1.1", "2.2.2.2", "1.1.1.1", None]

    async def fetcher(proxy_config, index):
        ip = ips[index - 1]
        return ProxyPoolAttempt(
            index=index,
            proxy_label=f"{proxy_config['host']}:{proxy_config['port']}",
            exit_ip=ip,
            latency_ms=10.0,
            error_message=None if ip else "failed",
        )

    report = await check_proxy_pool(
        [{"type": "http", "host": "proxy.example", "port": 8080}],
        mode="rotating",
        request_count=4,
        fetcher=fetcher,
    )

    assert report.total == 4
    assert report.unique_count == 2
    assert report.duplicate_count == 1
    assert report.error_count == 1


@pytest.mark.asyncio
async def test_sticky_pool_checks_each_proxy_once():
    ips = ["10.0.0.1", "10.0.0.1", "10.0.0.2"]

    async def fetcher(proxy_config, index):
        return ProxyPoolAttempt(
            index=index,
            proxy_label=f"{proxy_config['host']}:{proxy_config['port']}",
            exit_ip=ips[index - 1],
            latency_ms=10.0,
        )

    report = await check_proxy_pool(
        [
            {"type": "socks5", "host": "proxy-1.example", "port": 1080},
            {"type": "socks5", "host": "proxy-2.example", "port": 1080},
            {"type": "socks5", "host": "proxy-3.example", "port": 1080},
        ],
        mode="sticky",
        fetcher=fetcher,
    )

    assert report.total == 3
    assert report.unique_count == 2
    assert report.duplicate_count == 1
    assert report.error_count == 0


@pytest.mark.asyncio
async def test_rotating_pool_requires_positive_request_count():
    with pytest.raises(ValueError, match="Number of requests"):
        await check_proxy_pool(
            [{"type": "http", "host": "proxy.example", "port": 8080}],
            mode="rotating",
            request_count=0,
        )
