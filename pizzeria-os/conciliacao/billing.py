"""Camada de cobrança (Prompt Mestre §6 do PRD, §8.2, §9.3, §10).

Invariantes aplicadas aqui:
 * INV-4: a base da captura é apenas `confirmed` (nunca `detected`);
 * INV-8: o braço variável só abre com flag variable_capture_enabled + histórico mínimo
   (ciclos conciliados e confirmações) — guarda de serviço, testada;
 * pré-requisitos de qualquer billing_charge: linha de flags do tenant, attribution_contract aceito
   e tenant ativo (também garantidos por trigger no banco).

Faixas "decrescentes" são aplicadas de forma MARGINAL (como IR): a alíquota de cada faixa incide só
sobre a fatia dentro dela. Em degrau, recuperar R$ 2.001 custaria R$ 160 e R$ 2.000 custaria R$ 300.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .flags import Flag, FlagService
from .gateways.mercadopago import BillingGateway
from .ledger import RecoveryLedgerService
from .models import AttributionContract, BillingCharge, ChargeStatus, ChargeType
from .money import apply_bps


class BillingError(ValueError):
    pass


@dataclass(frozen=True)
class Tier:
    up_to_cents: int | None
    rate_bps: int


@dataclass(frozen=True)
class PricingPlan:
    """Valores ILUSTRATIVOS — calibrar com dados próprios na Fase 2."""
    floor_cents: int = 12_900
    tiers: tuple[Tier, ...] = (Tier(50_000, 2500), Tier(200_000, 1500), Tier(None, 800))
    variable_cap_cents: int = 45_000
    min_reconciled_cycles: int = 3
    min_confirmed_entries: int = 10

    def __post_init__(self):
        bounds = [t.up_to_cents for t in self.tiers]
        if bounds[-1] is not None or any(b is None for b in bounds[:-1]):
            raise BillingError("apenas a última faixa pode ser ilimitada")
        if bounds[:-1] != sorted(bounds[:-1]):
            raise BillingError("faixas devem ser crescentes")
        rates = [t.rate_bps for t in self.tiers]
        if rates != sorted(rates, reverse=True):
            raise BillingError("faixas devem ser decrescentes em alíquota")


def compute_variable(base_cents: int, plan: PricingPlan) -> tuple[int, bool, list[dict]]:
    if type(base_cents) is not int or base_cents < 0:
        raise BillingError("base deve ser int não negativo")
    remaining, lower, total, breakdown = base_cents, 0, 0, []
    for t in plan.tiers:
        if remaining <= 0:
            break
        width = remaining if t.up_to_cents is None else min(remaining, t.up_to_cents - lower)
        part = apply_bps(width, t.rate_bps)
        breakdown.append({"from_cents": lower, "slice_cents": width, "rate_bps": t.rate_bps, "charge_cents": part})
        total += part
        remaining -= width
        lower = t.up_to_cents or lower
    capped = total > plan.variable_cap_cents
    return (plan.variable_cap_cents if capped else total), capped, breakdown


@dataclass
class TenantBillingContext:
    tenant_id: str
    active: bool
    contract: AttributionContract | None
    reconciled_cycles: int


@dataclass
class BillingService:
    flags: FlagService
    plan: PricingPlan = field(default_factory=PricingPlan)

    def _common_guards(self, ctx: TenantBillingContext) -> None:
        if not self.flags.has(ctx.tenant_id):
            raise BillingError("tenant sem tenant_feature_flags definidas — nenhuma billing_charge pode ser escrita")
        if ctx.contract is None or ctx.contract.tenant_id != ctx.tenant_id:
            raise BillingError("attribution_contract não aceito — cobrança juridicamente exposta")
        if not ctx.active:
            raise BillingError("tenant não está em modo ativo (onboarding incompleto ou em calibração)")

    def variable_blockers(self, ctx: TenantBillingContext, ledger: RecoveryLedgerService) -> list[str]:
        b = []
        if not self.flags.is_on(ctx.tenant_id, Flag.VARIABLE_CAPTURE_ENABLED):
            b.append("variable_capture_enabled=false (roadmap: piso primeiro)")
        if ctx.reconciled_cycles < self.plan.min_reconciled_cycles:
            b.append(f"histórico insuficiente: {ctx.reconciled_cycles}/{self.plan.min_reconciled_cycles} ciclos conciliados")
        if ledger.count_confirmed() < self.plan.min_confirmed_entries:
            b.append(f"confirmações insuficientes no ledger: {ledger.count_confirmed()}/{self.plan.min_confirmed_entries}")
        return b

    def gateway_for(self, tenant_id: str, single: BillingGateway, two: BillingGateway) -> BillingGateway:
        return single if self.flags.is_on(tenant_id, Flag.BILLING_SINGLE_MANDATE) else two

    def emit_floor(self, ctx: TenantBillingContext, period_id: str, gateway: BillingGateway | None) -> BillingCharge:
        self._common_guards(ctx)
        c = BillingCharge(ctx.tenant_id, ChargeType.PISO, period_id, self.plan.floor_cents, self.plan.floor_cents, False)
        if gateway is not None:
            c.gateway_ref = gateway.charge_floor(ctx.tenant_id, period_id, c.computed_amount_cents)
            c.instrument = gateway.instrument_floor
            c.status = ChargeStatus.SUBMITTED
        return c

    def preview_variable(self, ledger: RecoveryLedgerService, period_id: str, until: datetime | None = None) -> BillingCharge:
        entries = ledger.confirmed_unbilled(until)
        base = sum(e.amount_cents for e in entries)
        amount, capped, breakdown = compute_variable(base, self.plan)
        return BillingCharge(ledger.tenant_id, ChargeType.VARIAVEL, period_id, base, amount, capped,
                             ledger_entry_ids=[e.id for e in entries], breakdown=breakdown)

    def emit_variable(self, ctx: TenantBillingContext, ledger: RecoveryLedgerService, period_id: str,
                      gateway: BillingGateway, at: datetime, until: datetime | None = None) -> BillingCharge | None:
        self._common_guards(ctx)
        blockers = self.variable_blockers(ctx, ledger)
        if blockers:
            raise BillingError("; ".join(blockers))
        charge = self.preview_variable(ledger, period_id, until)
        if not charge.ledger_entry_ids:
            return None  # CT-B.2: sem entradas confirmed no período, não há cobrança variável
        for eid in charge.ledger_entry_ids:  # INV-4, defesa em profundidade
            entry = next(e for e in ledger.entries if e.id == eid)
            if entry.state.value != "confirmed":
                raise BillingError("tentativa de cobrar sobre entrada não confirmada")
        charge.gateway_ref = gateway.charge_variable(ctx.tenant_id, period_id, self.plan.floor_cents,
                                                     charge.computed_amount_cents)
        charge.instrument = gateway.instrument_variable
        charge.status = ChargeStatus.SUBMITTED
        by_id = {e.id: e.exception_id for e in ledger.entries}
        for eid in charge.ledger_entry_ids:
            ledger.mark_billed(by_id[eid], charge.id, at)
        return charge
