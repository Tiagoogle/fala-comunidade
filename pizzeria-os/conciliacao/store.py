"""Persistência em memória com isolamento por tenant na camada de aplicação (INVARIANTE 2).

Não existe método de leitura sem tenant: a única porta de entrada é Store.tenant(tenant_id), que
recusa tenant vazio. Produção: Postgres com as migrations em db/migrations (RLS é a segunda barreira).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .fees import FeeRuleBook
from .flags import FlagService
from .ledger import RecoveryLedgerService
from .models import (
    AttributionContract, BankTransaction, BillingCharge, ExpectedReceivable, ReconciliationException,
    ReconciliationMatch, SettlementLine,
)
from .onboarding import OnboardingState, TenantProfile
from .subset_sum import SolveResult


class TenantIsolationError(PermissionError):
    pass


@dataclass
class TenantData:
    profile: TenantProfile
    onboarding: OnboardingState
    ledger: RecoveryLedgerService
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
    subset_results: dict[str, SolveResult] = field(default_factory=dict)


class Store:
    def __init__(self, flags: FlagService) -> None:
        self.flags = flags
        self.fee_rules = FeeRuleBook()
        self._data: dict[str, TenantData] = {}

    def create_tenant(self, profile: TenantProfile) -> TenantData:
        if profile.tenant_id in self._data:
            raise ValueError("tenant já existe")
        self.flags.init_tenant(profile.tenant_id)
        td = TenantData(profile, OnboardingState(profile.tenant_id), RecoveryLedgerService(profile.tenant_id, self.flags))
        self._data[profile.tenant_id] = td
        return td

    def tenant(self, tenant_id: str) -> TenantData:
        if not tenant_id or not str(tenant_id).strip():
            raise TenantIsolationError("tenant_id obrigatório em toda leitura/escrita")
        try:
            return self._data[tenant_id]
        except KeyError:
            raise LookupError(f"tenant {tenant_id!r} inexistente") from None

    def exists(self, tenant_id: str) -> bool:
        return tenant_id in self._data

    @staticmethod
    def check(tenant_id: str, items) -> None:
        for it in items:
            if it.tenant_id != tenant_id:
                raise TenantIsolationError("tentativa de gravar item de outro tenant")
