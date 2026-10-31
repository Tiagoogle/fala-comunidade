"""Onboarding do lojista — 5 etapas sequenciais e retomáveis (Prompt Mestre §9).

Cada etapa persiste estado em tenant_onboarding_state. A ordem é forçada: não se avança sem a
anterior, e a Etapa 4 é PROIBIDA sem aceite do attribution_contract (também garantido no banco).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import IntEnum

from .models import AttributionContract, Channel, CommissionBase, FeeRule


class Step(IntEnum):
    TENANT_REGISTERED = 1
    FEE_CONTRACT = 2
    ATTRIBUTION_ACCEPTED = 3
    INTEGRATIONS_CONNECTED = 4
    CALIBRATION_DONE = 5


class OnboardingError(ValueError):
    pass


def valid_cnpj(cnpj: str) -> bool:
    d = re.sub(r"\D", "", cnpj or "")
    if len(d) != 14 or d == d[0] * 14:
        return False
    def dv(digits, weights):
        r = sum(int(x) * w for x, w in zip(digits, weights)) % 11
        return "0" if r < 2 else str(11 - r)
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    w2 = [6] + w1
    return d[12] == dv(d[:12], w1) and d[13] == dv(d[:13], w2)


@dataclass
class TenantProfile:
    tenant_id: str
    name: str
    cnpj: str
    address: str
    legal_representative: str
    contact_email: str
    created_at: datetime


@dataclass
class OnboardingState:
    tenant_id: str
    completed: set[Step] = field(default_factory=set)
    history: list[dict] = field(default_factory=list)
    calibration_summary: dict | None = None

    @property
    def next_step(self) -> Step | None:
        for s in Step:
            if s not in self.completed:
                return s
        return None

    @property
    def active(self) -> bool:
        return self.next_step is None

    def require(self, step: Step) -> None:
        if step in self.completed:
            raise OnboardingError(f"etapa {step.value} já concluída")
        if self.next_step is not step:
            raise OnboardingError(f"etapa {step.value} fora de ordem; próxima é {self.next_step.value if self.next_step else '—'}")

    def complete(self, step: Step, at: datetime, **detail) -> None:
        self.completed.add(step)
        self.history.append({"step": step.value, "name": step.name.lower(), "at": at.isoformat(), **detail})


def make_fee_rule(tenant_id: str, onboarding_date: date, channel: Channel, commission_bps: int,
                  commission_base: CommissionBase, fixed_fee_cents: int, promo_platform_share_bps: int,
                  refund_reverses_commission: bool = True) -> FeeRule:
    """Versão 1: valid_from = data do onboarding, valid_to = None."""
    return FeeRule(tenant_id, channel, commission_bps, commission_base, fixed_fee_cents, promo_platform_share_bps,
                   onboarding_date, None, 1, refund_reverses_commission)


def make_contract(tenant_id: str, terms_version: str, recovered_definition: str, accepted_by: str,
                  accepted_ip: str, at: datetime) -> AttributionContract:
    if len(recovered_definition.strip()) < 40:
        raise OnboardingError("recovered_definition precisa do texto integral da cláusula")
    if not accepted_by or not accepted_ip:
        raise OnboardingError("aceite exige responsável legal e IP")
    return AttributionContract(tenant_id, at, terms_version, recovered_definition.strip(), accepted_by, accepted_ip)


DEFAULT_RECOVERED_DEFINITION = (
    "Considera-se valor recuperado por ação do módulo toda divergência tipada pelo motor de conciliação "
    "e registrada como confirmada no ledger de recuperação, independentemente de o lojista ter aberto, em "
    "paralelo, chamado próprio junto à plataforma."
)
