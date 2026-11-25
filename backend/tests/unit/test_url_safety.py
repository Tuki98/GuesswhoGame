"""Tests for SSRF-resistant image URL validation and resolution."""

from __future__ import annotations

import pytest

from app.core import url_safety
from app.core.url_safety import (
    MAX_URL_LENGTH,
    UnsafeUrlError,
    system_resolver,
    validate_and_resolve,
    validate_public_ip,
)

PUBLIC_IP = "93.184.216.34"


def public_resolver(_host: str, _port: int) -> list[str]:
    return [PUBLIC_IP]


def test_public_http_and_https_urls_are_pinned_to_resolved_addresses() -> None:
    target = validate_and_resolve(
        "http://images.example.com:80/a/b.png?size=large",
        resolver=public_resolver,
    )

    assert target.scheme == "http"
    assert target.host == "images.example.com"
    assert target.port == 80
    assert target.ip == PUBLIC_IP
    assert target.request_target == "/a/b.png?size=large"
    assert target.host_header == "images.example.com"

    secure = validate_and_resolve("https://images.example.com", resolver=public_resolver)
    assert secure.port == 443
    assert secure.request_target == "/"


def test_public_ip_literals_skip_dns() -> None:
    def unexpected_resolver(_host: str, _port: int) -> list[str]:
        raise AssertionError("IP literals must not be resolved")

    target = validate_and_resolve(
        f"http://{PUBLIC_IP}/image.png",
        resolver=unexpected_resolver,
    )

    assert target.ip == PUBLIC_IP


def test_idna_hostnames_are_normalized() -> None:
    target = validate_and_resolve(
        "http://bücher.example/image.png",
        resolver=public_resolver,
    )

    assert target.host == "xn--bcher-kva.example"


def test_ipv4_mapped_public_ipv6_is_normalized() -> None:
    assert validate_public_ip(f"::ffff:{PUBLIC_IP}") == PUBLIC_IP


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "x" * (MAX_URL_LENGTH + 1),
        "http://example.com/\x00image.png",
        "ftp://example.com/image.png",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://",
        "http:///image.png",
        "http://user:password@example.com/image.png",
        "http://example.com:8080/image.png",
        "http://example.com:0/image.png",
        "http://example.com:not-a-port/image.png",
        "http://[::1/image.png",
        f"http://{'a' * 64}.example/image.png",
    ],
)
def test_invalid_or_unsafe_url_shapes_are_rejected(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_and_resolve(url, resolver=public_resolver)


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "api.localhost",
        "printer",
        "service.internal",
        "service.intranet",
        "service.lan",
        "service.home",
        "service.corp",
        "service.local",
    ],
)
def test_internal_hostnames_are_rejected(host: str) -> None:
    with pytest.raises(UnsafeUrlError, match="internal hostname"):
        validate_and_resolve(f"http://{host}/image.png", resolver=public_resolver)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "0.0.0.0",  # noqa: S104 (test value, not a bind address)
        "10.1.2.3",
        "172.16.0.1",
        "192.168.1.10",
        "169.254.169.254",
        "224.0.0.1",
        "255.255.255.255",
        "::1",
        "fc00::1",
        "fe80::1",
        "::ffff:127.0.0.1",
    ],
)
def test_non_public_ip_ranges_are_rejected(address: str) -> None:
    with pytest.raises(UnsafeUrlError, match="non-public address"):
        validate_public_ip(address)


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1"],
)
def test_ip_literal_urls_in_private_ranges_are_rejected(address: str) -> None:
    with pytest.raises(UnsafeUrlError, match="non-public address"):
        validate_and_resolve(
            f"http://[{address}]/image.png" if ":" in address else f"http://{address}/image.png"
        )


def test_dns_answers_are_all_validated() -> None:
    with pytest.raises(UnsafeUrlError, match="non-public address"):
        validate_and_resolve(
            "http://images.example.com/image.png",
            resolver=lambda _host, _port: [PUBLIC_IP, "10.0.0.5"],
        )


def test_empty_dns_answers_are_rejected() -> None:
    with pytest.raises(UnsafeUrlError, match="could not be resolved"):
        validate_and_resolve(
            "http://images.example.com/image.png",
            resolver=lambda _host, _port: [],
        )


def test_dns_failure_is_rejected() -> None:
    def failing_resolver(_host: str, _port: int) -> list[str]:
        raise OSError("resolver unavailable")

    with pytest.raises(UnsafeUrlError, match="could not be resolved"):
        validate_and_resolve(
            "http://images.example.com/image.png",
            resolver=failing_resolver,
        )


def test_non_ip_resolver_answer_is_rejected() -> None:
    with pytest.raises(UnsafeUrlError, match="invalid address"):
        validate_and_resolve(
            "http://images.example.com/image.png",
            resolver=lambda _host, _port: ["not-an-ip"],
        )


def test_system_resolver_returns_unique_string_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answers = [
        (2, 1, 6, "", ("93.184.216.34", 80)),
        (2, 1, 6, "", ("93.184.216.34", 80)),
        (10, 1, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", 80)),
    ]
    monkeypatch.setattr(url_safety.socket, "getaddrinfo", lambda *_args, **_kwargs: answers)

    assert system_resolver("images.example.com", 80) == [
        "93.184.216.34",
        "2606:2800:220:1:248:1893:25c8:1946",
    ]
