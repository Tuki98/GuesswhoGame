"""Fake DNS and HTTP transport for image-download tests.

No test using these helpers performs real DNS lookups or network requests.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.image_download import ImageDownloader

PUBLIC_TEST_IP = "93.184.216.34"


@dataclass
class FakeResponse:
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    _offset: int = 0

    def getheaders(self) -> list[tuple[str, str]]:
        return [(key, value) for key, value in self.headers.items()]

    def read(self, amount: int | None = None) -> bytes:
        if amount is None:
            amount = len(self.body) - self._offset
        chunk = self.body[self._offset : self._offset + amount]
        self._offset += len(chunk)
        return chunk


class FakeConnection:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.method: str | None = None
        self.url: str | None = None
        self.request_headers: dict[str, str] = {}
        self.closed = False

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        **_kwargs: object,
    ) -> None:
        self.method = method
        self.url = url
        self.request_headers = dict(headers or {})

    def getresponse(self) -> FakeResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


class FakeImageServer:
    """Serve scripted responses by request path and resolve to a public IP."""

    def __init__(self) -> None:
        self.routes: dict[str, FakeResponse] = {}
        self.resolved: list[tuple[str, int]] = []
        self.requested: list[str] = []
        self.connections: list[FakeConnection] = []
        self.ips: list[str] | None = None
        self.resolve_error: OSError | None = None

    def serve(
        self,
        path: str,
        body: bytes = b"",
        *,
        status: int = 200,
        content_type: str | None = "image/png",
        headers: dict[str, str] | None = None,
    ) -> FakeImageServer:
        merged: dict[str, str] = {}
        if content_type is not None:
            merged["Content-Type"] = content_type
        if headers:
            merged.update(headers)
        self.routes[path] = FakeResponse(status=status, headers=merged, body=body)
        return self

    def resolver(self, host: str, port: int) -> list[str]:
        self.resolved.append((host, port))
        if self.resolve_error is not None:
            raise self.resolve_error
        return list(self.ips) if self.ips is not None else [PUBLIC_TEST_IP]

    def connection_factory(self, target: object, timeout: float) -> FakeConnection:
        del timeout
        request_target = target.request_target
        self.requested.append(request_target)
        response = self.routes.get(request_target, FakeResponse(status=404))
        connection = FakeConnection(response)
        self.connections.append(connection)
        return connection

    def downloader(
        self,
        *,
        max_bytes: int = 5 * 1024 * 1024,
        timeout: float = 1.0,
    ) -> ImageDownloader:
        return ImageDownloader(
            timeout=timeout,
            max_bytes=max_bytes,
            resolver=self.resolver,
            connection_factory=self.connection_factory,  # type: ignore[arg-type]
        )
