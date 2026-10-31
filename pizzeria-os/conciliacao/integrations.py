"""Integrações externas: iFood (relatório financeiro) e armazenamento cifrado de tokens OAuth.

iFood: o layout real do relatório financeiro é parte da Incógnita 3 e NÃO foi verificado. O preset
abaixo é uma hipótese de colunas; ajustar na Fase 0 com um relatório real. O cliente OAuth é um
Protocol — sem endpoint inventado.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from cryptography.fernet import Fernet

from .canonical import SettlementColumnMap

IFOOD_REPORT_COLUMNS_HYPOTHESIS = SettlementColumnMap(
    order_ref="pedido", net="valor_liquido", line_type="tipo", settlement_date="data_repasse",
)


class IFoodFinancialClient(Protocol):
    def download_settlement_report(self, access_token: str, cycle_start: str) -> str: ...


@dataclass
class IntegrationTokenStore:
    """Tabela separada, cifrada em repouso (Fernet = AES-128-CBC + HMAC-SHA256).
    A chave vem de PIZZERIA_TOKEN_KEY (em produção: KMS/secret manager, rotação documentada)."""
    key: bytes = field(default_factory=lambda: os.environ.get("PIZZERIA_TOKEN_KEY", "").encode() or Fernet.generate_key())
    _rows: dict[tuple[str, str], dict] = field(default_factory=dict)

    def __post_init__(self):
        self._fernet = Fernet(self.key)

    def put(self, tenant_id: str, provider: str, access_token: str, refresh_token: str | None,
            expires_at: datetime | None) -> None:
        if not access_token:
            raise ValueError("token vazio")
        self._rows[(tenant_id, provider)] = {
            "access_token_enc": self._fernet.encrypt(access_token.encode()),
            "refresh_token_enc": self._fernet.encrypt(refresh_token.encode()) if refresh_token else None,
            "expires_at": expires_at,
        }

    def get_access_token(self, tenant_id: str, provider: str) -> str:
        return self._fernet.decrypt(self._rows[(tenant_id, provider)]["access_token_enc"]).decode()

    def needs_refresh(self, tenant_id: str, provider: str, now: datetime) -> bool:
        exp = self._rows[(tenant_id, provider)]["expires_at"]
        return exp is not None and exp <= now

    def has(self, tenant_id: str, provider: str) -> bool:
        return (tenant_id, provider) in self._rows

    def raw_row(self, tenant_id: str, provider: str) -> dict:
        return self._rows[(tenant_id, provider)]
