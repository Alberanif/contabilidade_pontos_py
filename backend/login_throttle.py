"""Limitador de tentativas de login em memória (issue #57).

Após `MAX_FAILURES` falhas em `WINDOW_SECONDS`, a chave (e-mail ou IP) fica
bloqueada por `LOCK_SECONDS`; durante o bloqueio nem a senha correta entra.
Estado por processo (não compartilhado entre réplicas). O relógio é injetável.
"""
import threading
import time
from collections import deque

from fastapi import Request

MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60
LOCK_SECONDS = 15 * 60
MAX_KEYS = 10_000


def client_ip(request: Request) -> str | None:
    """IP do cliente: primeiro valor de X-Forwarded-For; senão o IP da conexão."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else None


class LoginThrottle:
    def __init__(self, clock=time.monotonic, max_keys: int = MAX_KEYS):
        self._clock = clock
        self._max_keys = max_keys
        self._lock = threading.Lock()
        self._failures: dict[str, deque] = {}
        self._blocked_until: dict[str, float] = {}

    @staticmethod
    def _keys(email: str | None, ip: str | None) -> list[str]:
        keys = []
        if email:
            keys.append("e:" + email.strip().lower())
        if ip:
            keys.append("i:" + ip)
        return keys

    def is_blocked(self, email: str | None, ip: str | None) -> bool:
        now = self._clock()
        with self._lock:
            for key in self._keys(email, ip):
                until = self._blocked_until.get(key)
                if until is not None:
                    if until > now:
                        return True
                    del self._blocked_until[key]
            return False

    def record_failure(self, email: str | None, ip: str | None) -> None:
        now = self._clock()
        with self._lock:
            for key in self._keys(email, ip):
                q = self._failures.setdefault(key, deque())
                while q and now - q[0] >= WINDOW_SECONDS:
                    q.popleft()
                q.append(now)
                if len(q) >= MAX_FAILURES:
                    self._blocked_until[key] = now + LOCK_SECONDS
                    del self._failures[key]
            self._cleanup(now)

    def record_success(self, email: str | None) -> None:
        with self._lock:
            for key in self._keys(email, None):
                self._failures.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()
            self._blocked_until.clear()

    def _cleanup(self, now: float) -> None:
        """Remove entradas expiradas e, se ainda passar do limite, as mais antigas."""
        if len(self._failures) + len(self._blocked_until) <= self._max_keys:
            return
        for k in [k for k, u in self._blocked_until.items() if u <= now]:
            del self._blocked_until[k]
        for k in [k for k, q in self._failures.items() if not q or now - q[-1] >= WINDOW_SECONDS]:
            del self._failures[k]
        while len(self._failures) + len(self._blocked_until) > self._max_keys and self._failures:
            del self._failures[next(iter(self._failures))]


throttle = LoginThrottle()
