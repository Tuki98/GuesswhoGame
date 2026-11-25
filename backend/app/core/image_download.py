"""Bounded, SSRF-resistant image downloads."""

from __future__ import annotations

import http.client
import socket
import ssl
from collections.abc import Callable
from urllib.parse import urljoin, urlsplit

from app.core.images import ImageTooLargeError
from app.core.url_safety import (
    ResolvedTarget,
    Resolver,
    UnsafeUrlError,
    system_resolver,
    validate_and_resolve,
)

MAX_REDIRECTS = 3
_READ_CHUNK_BYTES = 64 * 1024
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_ALLOWED_CONTENT_TYPES = {"image/", "application/octet-stream"}
USER_AGENT = "GuessTheCharacter/0.1 image-fetcher"

ConnectionFactory = Callable[[ResolvedTarget, float], http.client.HTTPConnection]


class ImageDownloadError(ValueError):
    """Raised when an external image cannot be safely downloaded."""


def open_connection(
    target: ResolvedTarget,
    timeout: float,
) -> http.client.HTTPConnection:
    """Open a connection pinned to the validated IP.

    HTTPS is wrapped manually so SNI and certificate hostname checks still use
    the original hostname while the TCP connection goes to the validated IP.
    """
    if target.scheme == "https":
        raw_socket = socket.create_connection((target.ip, target.port), timeout=timeout)
        try:
            context = ssl.create_default_context()
            wrapped = context.wrap_socket(raw_socket, server_hostname=target.host)
        except Exception:
            raw_socket.close()
            raise
        connection = http.client.HTTPConnection(
            target.host,
            target.port,
            timeout=timeout,
        )
        connection.sock = wrapped
        return connection
    return http.client.HTTPConnection(target.ip, target.port, timeout=timeout)


def _read_limited(
    response: http.client.HTTPResponse,
    max_bytes: int,
) -> bytes:
    buffer = bytearray()
    while chunk := response.read(_READ_CHUNK_BYTES):
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise ImageTooLargeError(f"Image exceeds the {max_bytes // (1024 * 1024)} MB limit.")
    return bytes(buffer)


class ImageDownloader:
    """Download an external image while validating every network destination."""

    def __init__(
        self,
        *,
        timeout: float,
        max_bytes: int,
        resolver: Resolver = system_resolver,
        connection_factory: ConnectionFactory = open_connection,
    ) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.resolver = resolver
        self.connection_factory = connection_factory

    def download(self, url: str) -> bytes:
        current_url = url
        for _ in range(MAX_REDIRECTS + 1):
            target = validate_and_resolve(current_url, resolver=self.resolver)
            status, headers, body = self._request(target)
            if status in _REDIRECT_STATUSES:
                location = headers.get("location")
                if not location:
                    raise ImageDownloadError("Image URL redirected without a location.")
                next_url = urljoin(current_url, location)
                if target.scheme == "https" and urlsplit(next_url).scheme.lower() == "http":
                    raise ImageDownloadError("Image URL redirected to an insecure scheme.")
                current_url = next_url
                continue
            if status != 200:
                raise ImageDownloadError("Image URL returned an unsuccessful response.")
            return body
        raise ImageDownloadError("Image URL redirected too many times.")

    def _request(
        self,
        target: ResolvedTarget,
    ) -> tuple[int, dict[str, str], bytes]:
        connection: http.client.HTTPConnection | None = None
        try:
            connection = self.connection_factory(target, self.timeout)
            connection.request(
                "GET",
                target.request_target,
                headers={
                    "Host": target.host_header,
                    "User-Agent": USER_AGENT,
                    "Accept": "image/*",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            status = response.status
            headers = {key.lower(): value for key, value in response.getheaders()}

            if status in _REDIRECT_STATUSES or status != 200:
                return status, headers, b""

            content_type = headers.get("content-type", "").split(";")[0].strip().lower()
            if content_type and not content_type.startswith(tuple(_ALLOWED_CONTENT_TYPES)):
                raise ImageDownloadError("The URL did not return an image.")
            content_length = headers.get("content-length")
            if content_length:
                try:
                    declared_length = int(content_length)
                except ValueError as exc:
                    raise ImageDownloadError("The image response has an invalid size.") from exc
                if declared_length > self.max_bytes:
                    raise ImageTooLargeError(
                        f"Image exceeds the {self.max_bytes // (1024 * 1024)} MB limit."
                    )
            return status, headers, _read_limited(response, self.max_bytes)
        except (ImageTooLargeError, ImageDownloadError):
            raise
        except UnsafeUrlError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise ImageDownloadError("The image could not be downloaded.") from exc
        finally:
            if connection is not None:
                connection.close()
