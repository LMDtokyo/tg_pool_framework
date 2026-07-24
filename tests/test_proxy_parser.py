import pytest

from src.proxy.proxy_parser import parse_proxy_lines


pytestmark = pytest.mark.unit


def test_parse_proxy_lines_accepts_authenticated_and_open_proxies():
    proxies = parse_proxy_lines(
        "1.2.3.4:8080:user:pass\nproxy.example.com:3128",
        "HTTP",
    )

    assert proxies == [
        {
            "proxy_type": "http",
            "host": "1.2.3.4",
            "port": 8080,
            "username": "user",
            "password": "pass",
        },
        {
            "proxy_type": "http",
            "host": "proxy.example.com",
            "port": 3128,
            "username": "",
            "password": "",
        },
    ]


def test_parse_proxy_lines_deduplicates_the_same_endpoint_and_login():
    proxies = parse_proxy_lines(
        "1.2.3.4:1080:user:pass\n1.2.3.4:1080:user:pass",
        "socks5",
    )

    assert len(proxies) == 1


@pytest.mark.parametrize(
    "text",
    [
        "1.2.3.4:not-a-port",
        "1.2.3.4:70000",
        "1.2.3.4:1080:user",
        "1.2.3.4:1080::pass",
    ],
)
def test_parse_proxy_lines_rejects_invalid_lines(text):
    with pytest.raises(ValueError, match="line 1"):
        parse_proxy_lines(text, "socks5")


def test_parse_proxy_lines_rejects_unsupported_protocol():
    with pytest.raises(ValueError, match="http.*socks5"):
        parse_proxy_lines("1.2.3.4:1080", "socks4")
