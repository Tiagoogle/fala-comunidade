"""Feature flags das incógnitas bloqueadoras, por tenant (Prompt Mestre §8).

Os dois ramos de cada incógnita estão implementados; a flag escolhe qual roda em runtime.
Default false para tenants novos. Toda mudança é auditada (tenant_feature_flag_audit) e exige
autor + evidência — trocar de ramo sem evidência é exatamente o retrabalho que o §3 do PRD temia.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Flag(str, Enum):
    CONFIRMATION_METHOD_AUTO = "confirmation_method_auto"   # Incógnita 1
    BILLING_SINGLE_MANDATE = "billing_single_mandate"       # Incógnita 2
    SETTLEMENT_ITEMIZED = "settlement_itemized"             # Incógnita 3
    VARIABLE_CAPTURE_ENABLED = "variable_capture_enabled"   # Roadmap Fase 2 (não é incógnita)


INCOGNITA_FLAGS = (Flag.CONFIRMATION_METHOD_AUTO, Flag.BILLING_SINGLE_MANDATE, Flag.SETTLEMENT_ITEMIZED)

DESCRIPTIONS = {
    Flag.CONFIRMATION_METHOD_AUTO: "Incógnita 1 — iFood expõe ajuste rastreável por external_order_ref no ciclo de liquidação",
    Flag.BILLING_SINGLE_MANDATE: "Incógnita 2 — preapproval do Mercado Pago aceita valor variável no mesmo mandato",
    Flag.SETTLEMENT_ITEMIZED: "Incógnita 3 — relatório de repasse itemizado por pedido",
    Flag.VARIABLE_CAPTURE_ENABLED: "Fase 2 — braço variável (captura percentual) ativado",
}


@dataclass(frozen=True)
class FlagAudit:
    tenant_id: str
    flag: Flag
    old_value: bool
    new_value: bool
    changed_by: str
    changed_at: datetime
    evidence: str


@dataclass
class TenantFlags:
    values: dict[Flag, bool] = field(default_factory=lambda: {f: False for f in Flag})

    def __getitem__(self, flag: Flag) -> bool:
        return self.values[flag]


class FlagService:
    def __init__(self) -> None:
        self._flags: dict[str, TenantFlags] = {}
        self._audit: list[FlagAudit] = []

    def init_tenant(self, tenant_id: str) -> TenantFlags:
        if tenant_id in self._flags:
            raise ValueError("flags já inicializadas para o tenant")
        self._flags[tenant_id] = TenantFlags()
        return self._flags[tenant_id]

    def has(self, tenant_id: str) -> bool:
        return tenant_id in self._flags

    def get(self, tenant_id: str) -> TenantFlags:
        try:
            return self._flags[tenant_id]
        except KeyError:
            raise LookupError(f"tenant {tenant_id!r} sem linha em tenant_feature_flags") from None

    def is_on(self, tenant_id: str, flag: Flag) -> bool:
        return self.get(tenant_id)[flag]

    def set(self, tenant_id: str, flag: Flag, value: bool, changed_by: str, evidence: str, at: datetime) -> FlagAudit:
        if not changed_by:
            raise ValueError("mudança de flag exige autor")
        if not evidence or len(evidence.strip()) < 10:
            raise ValueError("mudança de flag exige evidência (ex.: ID do teste em sandbox, link da documentação)")
        tf = self.get(tenant_id)
        old = tf.values[flag]
        tf.values[flag] = value
        entry = FlagAudit(tenant_id, flag, old, value, changed_by, at, evidence.strip())
        self._audit.append(entry)
        return entry

    def audit(self, tenant_id: str) -> list[FlagAudit]:
        return [a for a in self._audit if a.tenant_id == tenant_id]

    def snapshot(self, tenant_id: str) -> dict:
        tf = self.get(tenant_id)
        return {f.value: {"value": tf[f], "description": DESCRIPTIONS[f]} for f in Flag}
