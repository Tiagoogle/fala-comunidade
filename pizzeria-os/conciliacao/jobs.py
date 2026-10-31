"""Fila assíncrona para trabalho pesado (SubsetSumSolver).

Em produção: RQ/Celery sobre Redis (ver ADR-001). A interface é mínima de propósito — o motor só
precisa enfileirar, saber o que está pendente e ser notificado quando um job termina.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .models import new_id


class JobQueue(Protocol):
    def enqueue(self, kind: str, key: str, fn: Callable[[], None]) -> str: ...
    def pending(self, kind: str) -> set[str]: ...


@dataclass
class InMemoryJobQueue:
    """Fila em processo. drain() executa os jobs — em testes, simula o worker."""
    _jobs: deque = field(default_factory=deque)
    _pending: dict[str, set[str]] = field(default_factory=dict)
    failures: list[tuple[str, str, str]] = field(default_factory=list)

    def enqueue(self, kind: str, key: str, fn: Callable[[], None]) -> str:
        bucket = self._pending.setdefault(kind, set())
        if key in bucket:
            return key  # idempotente: não enfileira o mesmo trabalho duas vezes
        bucket.add(key)
        self._jobs.append((new_id(), kind, key, fn))
        return key

    def pending(self, kind: str) -> set[str]:
        return set(self._pending.get(kind, set()))

    def drain(self) -> int:
        n = 0
        while self._jobs:
            job_id, kind, key, fn = self._jobs.popleft()
            try:
                fn()
            except Exception as exc:  # o job falho sai da fila e fica registrado; não derruba o worker
                self.failures.append((kind, key, repr(exc)))
            finally:
                self._pending[kind].discard(key)
            n += 1
        return n
