"""Persistência em memória com isolamento por tenant verificado na camada de aplicação.

Em produção, substituir por Postgres (db/schema.sql) — o RLS do banco é a segunda barreira,
não a única: toda leitura/escrita aqui exige o tenant explícito e recusa itens de outro tenant.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from .fees import FeeRuleBook
from .gates import DecisionGates
from .ledger import RecoveryLedger
from .models import (
    AttributionContract, BankTransaction, BillingCharge, ExpectedReceivable, ReconciliationException,
    ReconciliationMatch, SettlementLine,
)


@dataclass
class TenantData:
    expected: dict[str, ExpectedReceivable] = field(default_factory=dict)
    settlements: dict[str, SettlementLine] = field(default_factory=dict)
    bank: dict[str, BankTransaction] = field(default_factory=dict)
    matches: dict[str, ReconciliationMatch] = field(default_factory=dict)
    exceptions: dict[str, ReconciliationException] = field(default_factory=dict)
    exceptions_by_fp: dict[str, str] = field(default_factory=dict)
    charges: dict[str, BillingCharge] = field(default_factory=dict)
    contract: AttributionContract | None = None
    settlement_hashes: set[str] = field(default_factory=set)
    bank_hashes: set[str] = field(default_factory=set)
    order_event_keys: set[tuple] = field(default_factory=set)
    closed_cycles: set[str] = field(default_factory=set)
    reconciled_cycles: set[str] = field(default_factory=set)
    ledger: RecoveryLedger | None = None


class Store:
    def __init__(self, gates: DecisionGates) -> None:
        self.gates = gates
        self.fee_rules = FeeRuleBook()
        self._data: dict[str, TenantData] = defaultdict(TenantData)

    def tenant(self, tenant_id: str) -> TenantData:
        if not tenant_id or not tenant_id.strip():
            raise PermissionError("tenant_id obrigatório")
        td = self._data[tenant_id]
        if td.ledger is None:
            td.ledger = RecoveryLedger(tenant_id, self.gates)
        return td

    @staticmethod
    def _check(tenant_id: str, items) -> None:
        for it in items:
            if it.tenant_id != tenant_id:
                raise PermissionError("tentativa de gravar item de outro tenant")

    def add_expected(self, tenant_id: str, items: list[ExpectedReceivable]) -> None:
        self._check(tenant_id, items)
        td = self.tenant(tenant_id)
        for it in items:
            td.expected[it.id] = it

    def add_settlements(self, tenant_id: str, items: list[SettlementLine]) -> None:
        self._check(tenant_id, items)
        td = self.tenant(tenant_id)
        for it in items:
            td.settlements[it.id] = it

    def add_bank(self, tenant_id: str, items: list[BankTransaction]) -> None:
        self._check(tenant_id, items)
        td = self.tenant(tenant_id)
        for it in items:
            td.bank[it.id] = it

    def upsert_exceptions(self, tenant_id: str, items: list[ReconciliationException], at: datetime) -> list[ReconciliationException]:
        """Idempotente por fingerprint: reexecutar o motor atualiza, não duplica, e preserva status/histórico."""
        self._check(tenant_id, items)
        td = self.tenant(tenant_id)
        new = []
        for exc in items:
            existing_id = td.exceptions_by_fp.get(exc.fingerprint)
            if existing_id:
                cur = td.exceptions[existing_id]
                if cur.amount_cents != exc.amount_cents:
                    cur.log("amount_revised", "engine", at, old=cur.amount_cents, new=exc.amount_cents)
                    cur.amount_cents = exc.amount_cents
                cur.match_id = exc.match_id
                continue
            exc.log("created", "engine", at)
            td.exceptions[exc.id] = exc
            td.exceptions_by_fp[exc.fingerprint] = exc.id
            new.append(exc)
        return new
