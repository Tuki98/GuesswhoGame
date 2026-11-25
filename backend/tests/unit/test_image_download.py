"""Tests for bounded, redirect-safe image downloading."""

from __future__ import annotations

import http.client
import ssl
from unittest.mock import MagicMock

import pytest

from app.core import image_download
from app.core.image_download import (
    ImageDownloader,
    ImageDownloadError,
    open_connection,
)
from app.core.images import ImageTooLargeError
from app.core.url_safety import ResolvedTarget, UnsafeUrlError
from tests.fake_http import PUBLIC_TEST_IP, FakeConnection, FakeImageServer
from tests.image_helpers import image_bytes


def test_successful_download_returns_body_and_closes_connection() -> None:
    server = FakeImageServer().serve("/image.png", image_bytes())

    body = server.downloader().download("http://images.example.com/image.png")

    assert body == server.routes["/image.png"].body
    assert server.resolved == [("images.example.com", 80)]
    assert server.requested == ["/image.png"]
    assert server.connections[0].url == "/image.png"
    assert server.connections[0].request_headers["Host"] == "images.example.com"
    assert server.connections[0].closed is True


def test_download_connects_to_the_resolved_ip() -> None:
    server = FakeImageServer().serve("/image.png", image_bytes())
    targets: list[ResolvedTarget] = []

    def factory(target: ResolvedTarget, timeout: float) -> FakeConnection:
        del timeout
        targets.append(target)
        return FakeConnection(server.routes[target.request_target])

    downloader = ImageDownloader(
        timeout=1,
        max_bytes=5 * 1024 * 1024,
        resolver=server.resolver,
        connection_factory=factory,  # type: ignore[arg-type]
    )

    downloader.download("http://images.example.com/image.png")

    assert targets[0].ip == PUBLIC_TEST_IP


def test_relative_and_absolute_redirects_are_followed_and_revalidated() -> None:
    server = FakeImageServer()
    server.serve("/start", status=302, headers={"Location": "/final"})
    server.serve("/final", image_bytes())

    body = server.downloader().download("http://images.example.com/start")

    assert body == server.routes["/final"].body
    assert server.requested == ["/start", "/final"]
    assert server.resolved == [
        ("images.example.com", 80),
        ("images.example.com", 80),
    ]

    absolute = FakeImageServer()
    absolute.serve(
        "/start",
        status=301,
        headers={"Location": "http://other.example/picture"},
    )
    absolute.serve("/picture", image_bytes())

    body = absolute.downloader().download("http://images.example.com/start")

    assert body == absolute.routes["/picture"].body
    assert absolute.resolved[-1] == ("other.example", 80)


def test_https_to_http_redirect_is_rejected() -> None:
    server = FakeImageServer().serve(
        "/start",
        status=302,
        headers={"Location": "http://images.example.com/final"},
    )

    with pytest.raises(ImageDownloadError, match="insecure scheme"):
        server.downloader().download("https://images.example.com/start")


def test_redirect_to_private_address_is_rejected() -> None:
    server = FakeImageServer().serve(
        "/start",
        status=302,
        headers={"Location": "http://127.0.0.1/internal"},
    )

    with pytest.raises(UnsafeUrlError, match="non-public address"):
        server.downloader().download("http://images.example.com/start")


def test_redirect_without_location_is_rejected() -> None:
    server = FakeImageServer().serve("/start", status=302)

    with pytest.raises(ImageDownloadError, match="without a location"):
        server.downloader().download("http://images.example.com/start")


def test_too_many_redirects_are_rejected() -> None:
    server = FakeImageServer()
    for index in range(4):
        server.serve(
            f"/r{index}",
            status=302,
            headers={"Location": f"/r{index + 1}"},
        )
    server.serve("/r4", image_bytes())

    with pytest.raises(ImageDownloadError, match="too many times"):
        server.downloader().download("http://images.example.com/r0")

    assert len(server.requested) == 4


@pytest.mark.parametrize("status", [204, 400, 404, 500])
def test_unsuccessful_status_is_rejected(status: int) -> None:
    server = FakeImageServer().serve("/image.png", status=status)

    with pytest.raises(ImageDownloadError, match="unsuccessful"):
        server.downloader().download("http://images.example.com/image.png")


def test_non_image_content_type_is_rejected() -> None:
    server = FakeImageServer().serve(
        "/image.png",
        b"<html></html>",
        content_type="text/html",
    )

    with pytest.raises(ImageDownloadError, match="did not return an image"):
        server.downloader().download("http://images.example.com/image.png")


@pytest.mark.parametrize("content_type", [None, "application/octet-stream"])
def test_missing_or_generic_content_types_are_allowed(content_type: str | None) -> None:
    server = FakeImageServer().serve(
        "/image.png",
        image_bytes(),
        content_type=content_type,
    )

    assert server.downloader().download("http://images.example.com/image.png")


def test_declared_content_length_over_limit_is_rejected() -> None:
    server = FakeImageServer().serve(
        "/image.png",
        image_bytes(),
        headers={"Content-Length": "999999"},
    )

    with pytest.raises(ImageTooLargeError, match="limit"):
        server.downloader(max_bytes=100).download("http://images.example.com/image.png")


def test_invalid_content_length_is_rejected() -> None:
    server = FakeImageServer().serve(
        "/image.png",
        image_bytes(),
        headers={"Content-Length": "not-a-number"},
    )

    with pytest.raises(ImageDownloadError, match="invalid size"):
        server.downloader().download("http://images.example.com/image.png")


def test_streamed_body_over_limit_is_rejected_without_content_length() -> None:
    server = FakeImageServer().serve("/image.png", b"x" * 200)

    with pytest.raises(ImageTooLargeError, match="limit"):
        server.downloader(max_bytes=100).download("http://images.example.com/image.png")


def test_dns_errors_are_wrapped() -> None:
    server = FakeImageServer()
    server.resolve_error = OSError("dns down")

    with pytest.raises(UnsafeUrlError, match="could not be resolved"):
        server.downloader().download("http://images.example.com/image.png")


def test_network_errors_are_wrapped() -> None:
    server = FakeImageServer()

    def failing_factory(_target: ResolvedTarget, _timeout: float) -> FakeConnection:
        raise OSError("connection refused")

    downloader = ImageDownloader(
        timeout=1,
        max_bytes=5 * 1024 * 1024,
        resolver=server.resolver,
        connection_factory=failing_factory,  # type: ignore[arg-type]
    )

    with pytest.raises(ImageDownloadError, match="could not be downloaded"):
        downloader.download("http://images.example.com/image.png")


def test_http_protocol_errors_are_wrapped() -> None:
    server = FakeImageServer()

    def failing_factory(_target: ResolvedTarget, _timeout: float) -> FakeConnection:
        raise http.client.HTTPException("broken")

    downloader = ImageDownloader(
        timeout=1,
        max_bytes=5 * 1024 * 1024,
        resolver=server.resolver,
        connection_factory=failing_factory,  # type: ignore[arg-type]
    )

    with pytest.raises(ImageDownloadError, match="could not be downloaded"):
        downloader.download("http://images.example.com/image.png")


def test_http_connection_is_pinned_to_the_resolved_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[tuple[str, int, float]] = []

    class FakeHTTPConnection:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            created.append((host, port, timeout))
            self.sock = None

    monkeypatch.setattr(image_download.http.client, "HTTPConnection", FakeHTTPConnection)
    target = ResolvedTarget(
        scheme="http",
        host="images.example.com",
        port=80,
        ip=PUBLIC_TEST_IP,
        request_target="/image.png",
        host_header="images.example.com",
    )

    connection = open_connection(target, 2.5)

    assert isinstance(connection, FakeHTTPConnection)
    assert created == [(PUBLIC_TEST_IP, 80, 2.5)]


def test_https_connection_pins_ip_but_verifies_original_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_socket = MagicMock(name="raw-socket")
    wrapped_socket = MagicMock(name="wrapped-socket")
    context = MagicMock(name="ssl-context")
    context.wrap_socket.return_value = wrapped_socket
    monkeypatch.setattr(
        image_download.socket, "create_connection", MagicMock(return_value=raw_socket)
    )
    monkeypatch.setattr(
        image_download.ssl, "create_default_context", MagicMock(return_value=context)
    )
    monkeypatch.setattr(
        image_download.http.client,
        "HTTPConnection",
        lambda host, port, timeout: MagicMock(name="connection", sock=None),
    )
    target = ResolvedTarget(
        scheme="https",
        host="images.example.com",
        port=443,
        ip=PUBLIC_TEST_IP,
        request_target="/image.png",
        host_header="images.example.com",
    )

    connection = open_connection(target, 3.0)

    image_download.socket.create_connection.assert_called_once_with(
        (PUBLIC_TEST_IP, 443),
        timeout=3.0,
    )
    context.wrap_socket.assert_called_once_with(
        raw_socket,
        server_hostname="images.example.com",
    )
    assert connection.sock is wrapped_socket


def test_https_wrap_failure_closes_the_raw_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_socket = MagicMock(name="raw-socket")
    context = MagicMock(name="ssl-context")
    context.wrap_socket.side_effect = ssl.SSLError("handshake failed")
    monkeypatch.setattr(
        image_download.socket, "create_connection", MagicMock(return_value=raw_socket)
    )
    monkeypatch.setattr(
        image_download.ssl, "create_default_context", MagicMock(return_value=context)
    )
    target = ResolvedTarget(
        scheme="https",
        host="images.example.com",
        port=443,
        ip=PUBLIC_TEST_IP,
        request_target="/image.png",
        host_header="images.example.com",
    )

    with pytest.raises(ssl.SSLError):
        open_connection(target, 3.0)

    raw_socket.close.assert_called_once_with()


def test_socket_creation_failure_is_wrapped_as_download_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = FakeImageServer()
    monkeypatch.setattr(
        image_download.socket,
        "create_connection",
        MagicMock(side_effect=OSError("no route")),
    )
    downloader = ImageDownloader(
        timeout=1,
        max_bytes=5 * 1024 * 1024,
        resolver=server.resolver,
    )

    with pytest.raises(ImageDownloadError, match="could not be downloaded"):
        downloader.download("https://images.example.com/image.png")
