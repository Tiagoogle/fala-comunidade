"""Camada de cobrança (PRD §6): piso de garantia + captura de valor sobre recuperado CONFIRMADO.

Invariantes:
 * a captura incide só sobre o estado `confirmed` do ledger — nunca sobre `detected`;
 * faixas são MARGINAIS (como IR): evita o degrau em que recuperar R$ 1 a mais reduz o valor líquido do lojista;
 * o teto limita apenas o componente variável;
 * o braço variável exige: Incógnita 2 resolvida + contrato de atribuição aceito + histórico mínimo
   de ciclos conciliados + ativação explícita. O piso é invariante às incógnitas (assinatura fixa nos dois ramos).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from .gates import DecisionGates, Gate
from .ledger import RecoveryLedger
from .models import AttributionContract, BillingCharge, ChargeStatus, ChargeType
from .money import apply_bps


class BillingError(ValueError):
    pass


@dataclass(frozen=True)
class Tier:
    up_to_cents: int | None   # None = sem limite superior
    rate_bps: int


@dataclass(frozen=True)
class PricingPlan:
    """Valores ILUSTRATIVOS do PRD — calibração pendente com dados reais de recuperação."""
    floor_cents: int = 12_900
    tiers: tuple[Tier, ...] = (Tier(50_000, 2500), Tier(200_000, 1500), Tier(None, 800))
    variable_cap_cents: int = 45_000
    variable_arm_enabled: bool = False          # rota de lançamento: piso sozinho primeiro
    min_reconciled_cycles_for_variable: int = 4

    def __post_init__(self):
        bounds = [t.up_to_cents for t in self.tiers]
        if bounds[-1] is not None or any(b is None for b in bounds[:-1]):
            raise BillingError("apenas a última faixa pode ser ilimitada")
        if bounds[:-1] != sorted(bounds[:-1]):
            raise BillingError("faixas devem ser crescentes")


def compute_variable(base_cents: int, plan: PricingPlan) -> tuple[int, bool, list[dict]]:
    """Retorna (valor, teto_aplicado, memória de cálculo por faixa)."""
    if base_cents < 0:
        raise BillingError("base negativa")
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


class BillingGateway(Protocol):
    """Adaptador de gateway. A implementação Mercado Pago depende de verificação em sandbox (Incógnita 2)."""

    def charge_subscription(self, tenant_id: str, amount_cents: int, period_id: str) -> str: ...
    def charge_variable(self, tenant_id: str, amount_cents: int, period_id: str) -> str: ...


@dataclass
class BillingService:
    gates: DecisionGates
    plan: PricingPlan = field(default_factory=PricingPlan)

    def floor_charge(self, tenant_id: str, period_id: str, gateway: BillingGateway | None = None) -> BillingCharge:
        charge = BillingCharge(tenant_id, ChargeType.FLOOR, period_id, self.plan.floor_cents,
                               self.plan.floor_cents, cap_applied=False)
        if gateway is not None:
            charge.gateway_ref = gateway.charge_subscription(tenant_id, charge.computed_amount_cents, period_id)
            charge.status = ChargeStatus.SUBMITTED
        return charge

    def variable_readiness(self, tenant_id: str, contract: AttributionContract | None,
                           reconciled_cycles: int) -> list[str]:
        blockers = []
        if not self.plan.variable_arm_enabled:
            blockers.append("braço variável desativado (rota de lançamento: piso primeiro)")
        if contract is None or contract.tenant_id != tenant_id:
            blockers.append("sem attribution_contract aceito — cobrança variável juridicamente exposta")
        if reconciled_cycles < self.plan.min_reconciled_cycles_for_variable:
            blockers.append(f"histórico insuficiente: {reconciled_cycles}/{self.plan.min_reconciled_cycles_for_variable} ciclos conciliados")
        return blockers

    def preview_variable(self, ledger: RecoveryLedger, period_id: str) -> BillingCharge:
        """Rascunho reconstruível: base = recuperado confirmado não faturado. Não toca o gateway nem o ledger."""
        entries = ledger.confirmed_unbilled()
        base = sum(e.amount_cents for e in entries)
        amount, capped, breakdown = compute_variable(base, self.plan)
        return BillingCharge(ledger.tenant_id, ChargeType.VARIABLE, period_id, base, amount, capped,
                             ledger_entry_ids=[e.id for e in entries], breakdown=breakdown)

    def emit_variable(self, ledger: RecoveryLedger, period_id: str, contract: AttributionContract | None,
                      reconciled_cycles: int, gateway: BillingGateway, at: datetime) -> BillingCharge:
        self.gates.require(Gate.GATEWAY_VARIABLE_AMOUNT, "emissão de cobrança variável no gateway")
        blockers = self.variable_readiness(ledger.tenant_id, contract, reconciled_cycles)
        if blockers:
            raise BillingError("; ".join(blockers))
        charge = self.preview_variable(ledger, period_id)
        if charge.computed_amount_cents == 0:
            return charge
        charge.gateway_ref = gateway.charge_variable(ledger.tenant_id, charge.computed_amount_cents, period_id)
        charge.status = ChargeStatus.SUBMITTED
        exc_ids = {e.id: e.exception_id for e in ledger.confirmed_unbilled()}
        for entry_id in charge.ledger_entry_ids:
            ledger.mark_billed(exc_ids[entry_id], charge.id, at)
        return charge
