from __future__ import annotations

import ipaddress
import re
import socket
import threading
import time
from collections.abc import Callable
from urllib.parse import urlsplit

from app.errors import ServiceError


def resolve_addresses(host: str) -> list[str]:
    try:
        return list(
            {result[4][0] for result in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
        )
    except OSError as exc:
        raise ServiceError(
            422, "unsafe_destination", "Destination cannot be safely resolved"
        ) from exc


class URLSafetyPolicy:
    def __init__(self, dns_check: bool = True, resolver: Callable = resolve_addresses):
        self.dns_check = dns_check
        self.resolver = resolver

    def validate(self, raw: str) -> str:
        if not raw or len(raw) > 2048 or any(ord(c) <= 32 or ord(c) == 127 for c in raw):
            raise ServiceError(
                422,
                "invalid_url",
                "URL is empty, oversized, or contains whitespace/control characters",
            )
        try:
            parts = urlsplit(raw)
            host = (parts.hostname or "").lower().rstrip(".")
            port = parts.port
        except ValueError as exc:
            raise ServiceError(422, "invalid_url", "Invalid destination host or port") from exc
        if parts.scheme.lower() not in {"http", "https"} or not host:
            raise ServiceError(
                422, "invalid_url", "An absolute HTTP or HTTPS destination is required"
            )
        if parts.username is not None or parts.password is not None:
            raise ServiceError(
                422, "unsafe_destination", "Embedded URL credentials are not allowed"
            )
        if port not in {None, 80, 443}:
            raise ServiceError(
                422, "unsafe_destination", "Only standard HTTP/HTTPS ports are allowed"
            )
        if (
            host == "localhost"
            or host.endswith((".localhost", ".local", ".internal"))
            or "." not in host
            and ":" not in host
        ):
            raise ServiceError(
                422, "unsafe_destination", "Local or internal destinations are not allowed"
            )
        try:
            address = ipaddress.ip_address(host)
            if not address.is_global:
                raise ServiceError(
                    422, "unsafe_destination", "Destination must use a globally routable address"
                )
        except ValueError:
            # Reject noncanonical numeric IP encodings such as hex/octal forms.
            if re.fullmatch(r"(0x[0-9a-f]+|[0-9.]+)", host):
                raise ServiceError(
                    422, "unsafe_destination", "Ambiguous numeric address is not allowed"
                )
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
                raise ServiceError(422, "invalid_url", "Use an ASCII/IDNA hostname")
            if self.dns_check:
                addresses = self.resolver(host)
                if not addresses or any(
                    not ipaddress.ip_address(item).is_global for item in addresses
                ):
                    raise ServiceError(
                        422, "unsafe_destination", "Destination resolves to a nonpublic address"
                    )
        return raw


class RateLimiter:
    def __init__(self, limit: int, window: int = 60):
        self.limit = limit
        self.window = window
        self._entries: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, timestamp: float | None = None) -> bool:
        bucket = int(time.time() if timestamp is None else timestamp) // self.window
        with self._lock:
            if len(self._entries) > 4096:
                self._entries = {k: v for k, v in self._entries.items() if v[0] == bucket}
            old, count = self._entries.get(key, (bucket, 0))
            count = count if old == bucket else 0
            if count >= self.limit:
                return False
            self._entries[key] = (bucket, count + 1)
            return True
