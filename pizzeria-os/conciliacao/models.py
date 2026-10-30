"""Entidades do modelo de dados (PRD §4). Todo valor monetário em centavos (_cents)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


def new_id() -> str:
    return uuid.uuid4().hex


class Channel(str, Enum):
    IFOOD = "ifood"
    RAPPI = "rappi"
    PROPRIO = "proprio"


class EventType(str, Enum):
    SALE = "sale"
    PROMO = "promo"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"  # só aparece em N2: ajustes/estornos liquidados pela plataforma


class CommissionBase(str, Enum):
    GROSS = "gross"                    # comissão sobre o bruto (preço de tabela)
    NET_OF_PROMO = "net_of_promo"      # comissão sobre o bruto menos o desconto promocional


class ExceptionType(str, Enum):
    TAXA_DIVERGENTE = "taxa_divergente"
    VENDA_SEM_REPASSE = "venda_sem_repasse"
    REPASSE_SEM_VENDA = "repasse_sem_venda"
    DERIVA_SISTEMATICA = "deriva_sistematica"   # extensão: deltas absorvidos pela tolerância com sinal consistente
    ANTECIPACAO = "antecipacao"                 # Passe 4 — bloqueado (Incógnita 3)
    DIFERENCA_CAIXA = "diferenca_caixa"         # Passe 4 — bloqueado (Incógnita 3)


class ExceptionStatus(str, Enum):
    OPEN = "open"
    HUMAN_QUEUE = "human_queue"
    IN_RECOVERY = "in_recovery"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class MatchMethod(str, Enum):
    KEY_EVENT = "key_event"            # (external_order_ref, event_type)
    KEY_ORDER = "key_order_aggregate"  # soma dos eventos do pedido contra soma das linhas do pedido


class MatchStatus(str, Enum):
    MATCHED = "matched"
    WITHIN_TOLERANCE = "matched_within_tolerance"
    DIVERGENT = "divergent"


@dataclass(frozen=True)
class FeeRule:
    """platform_fee_rules — contrato efetivo por canal, versionado no tempo. valid_to é exclusivo."""
    tenant_id: str
    channel: Channel
    commission_bps: int
    commission_base: CommissionBase
    fixed_fee_cents: int
    promo_platform_share_bps: int   # parcela do desconto promocional que cabe à plataforma (5000 = meio a meio)
    valid_from: date
    valid_to: date | None
    version: int
    refund_reverses_commission: bool = True
    id: str = field(default_factory=new_id)

    def covers(self, d: date) -> bool:
        return self.valid_from <= d and (self.valid_to is None or d < self.valid_to)


@dataclass(frozen=True)
class OrderEvent:
    """Evento financeiro de origem (PDV/pedido). É a entrada para calcular N1."""
    tenant_id: str
    order_id: str
    external_order_ref: str
    channel: Channel
    event_type: EventType          # SALE ou REFUND
    gross_cents: int               # bruto de tabela (venda) ou valor estornado (refund), sempre >= 0
    occurred_on: date
    promo_discount_cents: int = 0  # desconto promocional total concedido ao cliente no pedido


@dataclass(frozen=True)
class ExpectedReceivable:
    """expected_receivables (N1) — uma linha por evento financeiro, não por pedido."""
    tenant_id: str
    order_id: str
    external_order_ref: str
    channel: Channel
    event_type: EventType
    gross_cents: int
    expected_net_cents: int
    fee_rule_version_id: str
    cycle_id: str
    components: dict = field(default_factory=dict, compare=False, hash=False)
    id: str = field(default_factory=new_id)


@dataclass(frozen=True)
class SettlementLine:
    """settlement_lines (N2) — relatório de repasse da plataforma, parseado."""
    tenant_id: str
    channel: Channel
    external_order_ref: str | None
    settlement_cycle_id: str
    reported_net_cents: int
    line_type: EventType
    settlement_date: date
    source_hash: str
    raw_payload: dict = field(default_factory=dict, compare=False, hash=False)
    id: str = field(default_factory=new_id)


@dataclass(frozen=True)
class BankTransaction:
    """bank_transactions (N3) — extrato OFX/CSV."""
    tenant_id: str
    amount_cents: int
    value_date: date
    description: str
    source_hash: str
    id: str = field(default_factory=new_id)


@dataclass
class ReconciliationMatch:
    tenant_id: str
    expected_ids: list[str]
    settlement_line_ids: list[str]
    match_method: MatchMethod
    confidence: float
    delta_cents: int          # reportado - esperado (negativo = lojista recebeu menos)
    status: MatchStatus
    order_ref: str
    cycle_id: str
    bank_txn_id: str | None = None
    id: str = field(default_factory=new_id)


@dataclass
class ReconciliationException:
    tenant_id: str
    type: ExceptionType
    amount_cents: int         # valor em disputa, positivo = a favor do lojista
    order_ref: str | None
    cycle_id: str | None
    probable_cause: str
    status: ExceptionStatus = ExceptionStatus.OPEN
    match_id: str | None = None
    fingerprint: str = ""   # chave de idempotência: reexecutar o motor não duplica exceções
    resolution_history: list[dict] = field(default_factory=list)
    id: str = field(default_factory=new_id)

    def log(self, action: str, actor: str, at: datetime, **extra) -> None:
        self.resolution_history.append({"action": action, "actor": actor, "at": at.isoformat(), **extra})


@dataclass(frozen=True)
class AttributionContract:
    tenant_id: str
    accepted_at: datetime
    terms_version: str
    recovered_definition: str
    accepted_by: str
    id: str = field(default_factory=new_id)


class ChargeType(str, Enum):
    FLOOR = "floor"         # piso de garantia (assinatura fixa — invariante às Incógnitas)
    VARIABLE = "variable"   # captura de valor sobre recuperado confirmado (bloqueada: Incógnita 2 + rota de lançamento)


class ChargeStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PAID = "paid"
    FAILED = "failed"


@dataclass
class BillingCharge:
    tenant_id: str
    charge_type: ChargeType
    period_id: str
    base_amount_cents: int       # base: piso contratado ou recuperado confirmado do período
    computed_amount_cents: int   # cobrado após faixas e teto
    cap_applied: bool
    status: ChargeStatus = ChargeStatus.DRAFT
    gateway_ref: str | None = None
    ledger_entry_ids: list[str] = field(default_factory=list)
    breakdown: list[dict] = field(default_factory=list)
    id: str = field(default_factory=new_id)
