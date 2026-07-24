"""
tests/test_config.py — Unit tests for src/config.py.

Тестирует:
  1. Иммутабельность ProxyConfig (frozen=True): попытка изменить
     атрибут должна вызывать FrozenInstanceError.
  2. Иммутабельность AccountConfig.
  3. Иммутабельность TimingPolicy.
  4. Корректность session_path (property, не поле).
  5. Диапазон значений TimingPolicy.next_delay() и next_message_delay().
  6. __repr__ ProxyConfig не содержит пароль (безопасность логов).
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from src.config import AccountConfig, ProxyConfig, TimingPolicy


# ---------------------------------------------------------------------------
# ProxyConfig
# ---------------------------------------------------------------------------

class TestProxyConfigImmutability:
    """Гарантируем что frozen=True действительно работает."""

    def test_port_cannot_be_reassigned(self):
        """
        Попытка изменить port должна вызывать FrozenInstanceError.
        Это ключевой тест изоляции воркеров: никто не должен
        случайно подменить прокси после создания воркера.
        """
        proxy = ProxyConfig(host="127.0.0.1", port=1080)
        with pytest.raises(dataclasses.FrozenInstanceError):
            proxy.port = 9999  # type: ignore[misc]

    def test_host_cannot_be_reassigned(self):
        proxy = ProxyConfig(host="proxy.example.com", port=1080)
        with pytest.raises(dataclasses.FrozenInstanceError):
            proxy.host = "evil.example.com"  # type: ignore[misc]

    def test_username_cannot_be_reassigned(self):
        proxy = ProxyConfig(host="127.0.0.1", port=1080, username="alice")
        with pytest.raises(dataclasses.FrozenInstanceError):
            proxy.username = "bob"  # type: ignore[misc]

    def test_password_cannot_be_reassigned(self):
        proxy = ProxyConfig(host="127.0.0.1", port=1080, password="secret")
        with pytest.raises(dataclasses.FrozenInstanceError):
            proxy.password = "leaked"  # type: ignore[misc]

    def test_new_attribute_cannot_be_added(self):
        """frozen также запрещает добавление новых атрибутов."""
        proxy = ProxyConfig(host="127.0.0.1", port=1080)
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            proxy.new_field = "injected"  # type: ignore[attr-defined]


class TestProxyConfigValues:
    def test_optional_fields_default_to_none(self):
        proxy = ProxyConfig(host="127.0.0.1", port=1080)
        assert proxy.username is None
        assert proxy.password is None

    def test_repr_hides_password(self):
        """
        Пароль не должен появляться в repr.
        Это защита от утечки секретов в логи и трейсбэки.
        """
        proxy = ProxyConfig(
            host="proxy.example.com",
            port=1080,
            username="alice",
            password="super_secret_password",
        )
        representation = repr(proxy)
        assert "super_secret_password" not in representation
        assert "proxy.example.com" in representation  # host видим
        assert "alice" in representation              # username видим

    def test_proxy_equality(self):
        """Два ProxyConfig с одинаковыми полями должны быть равны."""
        p1 = ProxyConfig(host="127.0.0.1", port=1080, username="u", password="p")
        p2 = ProxyConfig(host="127.0.0.1", port=1080, username="u", password="p")
        assert p1 == p2

    def test_proxy_hashable(self):
        """frozen=True делает объект hashable → можно использовать в set/dict."""
        proxy = ProxyConfig(host="127.0.0.1", port=1080)
        proxy_set = {proxy}
        assert proxy in proxy_set

    def test_proxy_type_defaults_to_socks5(self):
        proxy = ProxyConfig(host="127.0.0.1", port=1080)
        assert proxy.proxy_type == "socks5"

    def test_repr_includes_proxy_type(self):
        proxy = ProxyConfig(host="127.0.0.1", port=1080, proxy_type="http")
        assert "http" in repr(proxy)


class TestProxyConfigAsTuple:
    def test_socks5_maps_to_pysocks_socks5(self):
        import socks
        proxy = ProxyConfig(host="127.0.0.1", port=1080, proxy_type="socks5")
        assert proxy.as_tuple()[0] == socks.SOCKS5

    def test_socks4_maps_to_pysocks_socks4(self):
        import socks
        proxy = ProxyConfig(host="127.0.0.1", port=1080, proxy_type="socks4")
        assert proxy.as_tuple()[0] == socks.SOCKS4

    def test_http_maps_to_pysocks_http(self):
        import socks
        proxy = ProxyConfig(host="127.0.0.1", port=1080, proxy_type="http")
        assert proxy.as_tuple()[0] == socks.HTTP

    def test_https_maps_to_pysocks_http(self):
        """PySocks has no distinct HTTPS-to-proxy type -- both map to HTTP CONNECT."""
        import socks
        proxy = ProxyConfig(host="127.0.0.1", port=1080, proxy_type="https")
        assert proxy.as_tuple()[0] == socks.HTTP

    def test_unknown_type_falls_back_to_socks5(self):
        import socks
        proxy = ProxyConfig(host="127.0.0.1", port=1080, proxy_type="carrier-pigeon")
        assert proxy.as_tuple()[0] == socks.SOCKS5

    def test_as_tuple_field_order(self):
        proxy = ProxyConfig(
            host="127.0.0.1", port=1080, username="u", password="p", proxy_type="socks5",
        )
        import socks
        assert proxy.as_tuple() == (socks.SOCKS5, "127.0.0.1", 1080, True, "u", "p")


# ---------------------------------------------------------------------------
# AccountConfig
# ---------------------------------------------------------------------------

class TestAccountConfigImmutability:
    def test_phone_identity_always_has_one_leading_plus(self):
        plain = AccountConfig(api_id=1, api_hash="h", phone="918295123844")
        prefixed = AccountConfig(api_id=1, api_hash="h", phone="+918295123844")

        assert plain.phone == "+918295123844"
        assert plain.phone == prefixed.phone

    def test_api_id_cannot_be_reassigned(self):
        account = AccountConfig(
            api_id=12345,
            api_hash="abc" * 11,
            phone="+79001234567",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            account.api_id = 99999  # type: ignore[misc]

    def test_phone_cannot_be_reassigned(self):
        account = AccountConfig(
            api_id=12345,
            api_hash="abc" * 11,
            phone="+79001234567",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            account.phone = "+70000000000"  # type: ignore[misc]


class TestAccountConfigSessionPath:
    def test_session_path_strips_plus(self):
        """+ убирается из номера телефона для валидного имени файла."""
        account = AccountConfig(
            api_id=1, api_hash="h", phone="+79001234567"
        )
        assert "+" not in account.session_path
        assert "79001234567" in account.session_path

    def test_session_path_uses_session_dir(self):
        account = AccountConfig(
            api_id=1, api_hash="h", phone="+79001234567",
            session_dir="custom_sessions"
        )
        assert account.session_path.startswith("custom_sessions/")

    def test_different_phones_different_paths(self):
        a1 = AccountConfig(api_id=1, api_hash="h", phone="+79001111111")
        a2 = AccountConfig(api_id=1, api_hash="h", phone="+79002222222")
        assert a1.session_path != a2.session_path


# ---------------------------------------------------------------------------
# TimingPolicy
# ---------------------------------------------------------------------------

class TestTimingPolicyImmutability:
    def test_base_delay_cannot_be_reassigned(self):
        policy = TimingPolicy(base_delay_sec=2.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            policy.base_delay_sec = 0.0  # type: ignore[misc]

    def test_jitter_cannot_be_reassigned(self):
        policy = TimingPolicy(jitter_sec=1.5)
        with pytest.raises(dataclasses.FrozenInstanceError):
            policy.jitter_sec = 999.0  # type: ignore[misc]


class TestTimingPolicyDelays:
    def test_next_delay_within_expected_range(self):
        """
        next_delay() должен возвращать значения в диапазоне
        [max(0.1, base - jitter), base + jitter].
        Запускаем 200 раз для статистической уверенности.
        """
        policy = TimingPolicy(base_delay_sec=2.0, jitter_sec=1.5)
        max_expected = policy.base_delay_sec + policy.jitter_sec
        min_expected = 0.1  # clamp снизу

        for _ in range(200):
            d = policy.next_delay()
            assert min_expected <= d <= max_expected + 0.001, (
                f"next_delay()={d} out of [{min_expected}, {max_expected}]"
            )

    def test_next_message_delay_within_expected_range(self):
        policy = TimingPolicy(
            inter_message_delay_sec=3.0,
            inter_message_jitter_sec=2.0,
        )
        max_expected = policy.inter_message_delay_sec + policy.inter_message_jitter_sec
        min_expected = 0.5

        for _ in range(200):
            d = policy.next_message_delay()
            assert min_expected <= d <= max_expected + 0.001

    def test_next_delay_not_negative(self):
        """Даже при огромном jitter задержка не уходит в отрицательную область."""
        policy = TimingPolicy(base_delay_sec=0.1, jitter_sec=100.0)
        for _ in range(100):
            assert policy.next_delay() >= 0.1

    def test_startup_jitter_within_range(self):
        policy = TimingPolicy(startup_jitter_max_sec=5.0)
        for _ in range(100):
            j = policy.startup_jitter()
            assert 0.0 <= j <= 5.0
