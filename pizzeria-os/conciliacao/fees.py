"""N1 — cálculo da expectativa a partir do contrato versionado (platform_fee_rules)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .models import (
    Channel, CommissionBase, EventType, ExpectedReceivable, FeeRule, OrderEvent,
)
from .money import BPS, apply_bps


class FeeRuleError(ValueError):
    pass


@dataclass(frozen=True)
class CycleCalendar:
    """Mapeia datas para ciclos de repasse. Periodicidade por canal é parâmetro de contrato, não constante."""
    length_days: int = 7
    anchor: date = date(2026, 1, 5)  # segunda-feira

    def cycle_id(self, channel: Channel, d: date) -> str:
        offset = (d - self.anchor).days // self.length_days
        start = self.anchor + timedelta(days=offset * self.length_days)
        return f"{channel.value}:{start.isoformat()}"


class FeeRuleBook:
    """Regras versionadas no tempo. Recusa sobreposição de vigência — ambiguidade contratual é bug, não detalhe."""

    def __init__(self) -> None:
        self._rules: list[FeeRule] = []

    def add(self, rule: FeeRule) -> FeeRule:
        if not (0 <= rule.commission_bps <= BPS and 0 <= rule.promo_platform_share_bps <= BPS):
            raise FeeRuleError("percentuais devem estar entre 0 e 10000 bps")
        if rule.fixed_fee_cents < 0:
            raise FeeRuleError("taxa fixa negativa")
        if rule.valid_to is not None and rule.valid_to <= rule.valid_from:
            raise FeeRuleError("valid_to deve ser posterior a valid_from")
        for r in self._rules:
            if r.tenant_id != rule.tenant_id or r.channel != rule.channel:
                continue
            if r.version == rule.version:
                raise FeeRuleError(f"versão {rule.version} já existe para {rule.channel.value}")
            r_end = r.valid_to or date.max
            n_end = rule.valid_to or date.max
            if rule.valid_from < r_end and r.valid_from < n_end:
                raise FeeRuleError(
                    f"vigência sobreposta com versão {r.version} ({r.valid_from}..{r.valid_to}); "
                    "encerre a vigência anterior antes de criar a nova"
                )
        self._rules.append(rule)
        return rule

    def effective(self, tenant_id: str, channel: Channel, on: date) -> FeeRule:
        for r in self._rules:
            if r.tenant_id == tenant_id and r.channel == channel and r.covers(on):
                return r
        raise FeeRuleError(f"sem regra tarifária vigente para {channel.value} em {on.isoformat()}")

    def all(self, tenant_id: str) -> list[FeeRule]:
        return [r for r in self._rules if r.tenant_id == tenant_id]


def compute_expected(event: OrderEvent, rule: FeeRule, calendar: CycleCalendar) -> list[ExpectedReceivable]:
    """Gera uma ExpectedReceivable por evento financeiro.

    Venda:  sale  = bruto - comissão - taxa fixa
            promo = -(parcela do desconto que contratualmente cabe ao lojista)
    Estorno: refund = -(valor estornado) + comissão revertida (se o contrato prevê reversão)
    """
    if event.tenant_id != rule.tenant_id or event.channel != rule.channel:
        raise FeeRuleError("regra não pertence ao tenant/canal do evento")
    if event.gross_cents < 0 or event.promo_discount_cents < 0:
        raise FeeRuleError("bruto e desconto devem ser não negativos; o sinal é dado pelo event_type")
    if event.promo_discount_cents > event.gross_cents:
        raise FeeRuleError("desconto maior que o bruto")

    cycle = calendar.cycle_id(event.channel, event.occurred_on)
    common = dict(
        tenant_id=event.tenant_id, order_id=event.order_id,
        external_order_ref=event.external_order_ref, channel=event.channel,
        fee_rule_version_id=rule.id, cycle_id=cycle,
    )

    if event.event_type is EventType.SALE:
        base = event.gross_cents
        if rule.commission_base is CommissionBase.NET_OF_PROMO:
            base -= event.promo_discount_cents
        commission = apply_bps(base, rule.commission_bps)
        sale_net = event.gross_cents - commission - rule.fixed_fee_cents
        out = [ExpectedReceivable(
            event_type=EventType.SALE, gross_cents=event.gross_cents, expected_net_cents=sale_net,
            components={"commission_cents": commission, "fixed_fee_cents": rule.fixed_fee_cents,
                        "commission_bps": rule.commission_bps, "commission_base": rule.commission_base.value},
            **common,
        )]
        if event.promo_discount_cents:
            platform_share = apply_bps(event.promo_discount_cents, rule.promo_platform_share_bps)
            merchant_share = event.promo_discount_cents - platform_share
            out.append(ExpectedReceivable(
                event_type=EventType.PROMO, gross_cents=0, expected_net_cents=-merchant_share,
                components={"promo_discount_cents": event.promo_discount_cents,
                            "platform_share_cents": platform_share, "merchant_share_cents": merchant_share},
                **common,
            ))
        return out

    if event.event_type is EventType.REFUND:
        reversal = apply_bps(event.gross_cents, rule.commission_bps) if rule.refund_reverses_commission else 0
        return [ExpectedReceivable(
            event_type=EventType.REFUND, gross_cents=-event.gross_cents,
            expected_net_cents=-event.gross_cents + reversal,
            components={"commission_reversal_cents": reversal},
            **common,
        )]

    raise FeeRuleError(f"event_type {event.event_type.value} não gera expectativa")
