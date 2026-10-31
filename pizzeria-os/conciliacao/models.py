"""Entidades do modelo de dados (Prompt Mestre §5). Todo valor monetário em centavos (_cents).

INVARIANTE 1: campos *_cents são validados em runtime — float, Decimal ou bool são rejeitados
na construção do objeto, em qualquer camada.
"""
from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


def new_id() -> str:
    return uuid.uuid4().hex


class CentsTypeError(TypeError):
    pass


def check_cents(obj) -> None:
    for f in dataclasses.fields(obj):
        if not f.name.endswith("_cents"):
            continue
        v = getattr(obj, f.name)
        if v is None and f.name in getattr(obj, "_nullable_cents", ()):
            continue
        if type(v) is not int:  # exclui bool, float, Decimal
            raise CentsTypeError(f"{type(obj).__name__}.{f.name} deve ser int em centavos, recebeu {type(v).__name__}")


class _Cents:
    def __post_init__(self):
        check_cents(self)


class Channel(str, Enum):
    IFOOD = "ifood"
    RAPPI = "rappi"
    PROPRIO = "proprio"


class EventType(str, Enum):
    SALE = "sale"
    PROMO = "promo"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"  # só em N2: ajustes/estornos liquidados pela plataforma


class CommissionBase(str, Enum):
    GROSS = "gross"
    NET_OF_PROMO = "net_of_promo"


class ExceptionType(str, Enum):
    TAXA_DIVERGENTE = "taxa_divergente"
    VENDA_SEM_REPASSE = "venda_sem_repasse"
    REPASSE_SEM_VENDA = "repasse_sem_venda"
    ANTECIPACAO = "antecipacao"
    DIFERENCA_CAIXA = "diferenca_caixa"
    DERIVA_SISTEMATICA = "deriva_sistematica"  # extensão: deltas absorvidos com sinal consistente


RECOVERABLE_TYPES = {
    ExceptionType.TAXA_DIVERGENTE, ExceptionType.VENDA_SEM_REPASSE,
    ExceptionType.DIFERENCA_CAIXA, ExceptionType.DERIVA_SISTEMATICA,
}


class ExceptionStatus(str, Enum):
    OPEN = "open"
    HUMAN_QUEUE = "human_queue"
    IN_RECOVERY = "in_recovery"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class MatchMethod(str, Enum):
    KEY_EVENT = "key_event"              # Passe 1: (external_order_ref, event_type)
    KEY_ORDER = "key_order_aggregate"    # Passe 1: promo líquida dentro da linha de venda
    KEY_LOOSE = "key_loose"              # Passe 3: re-canonicalização antes da fila humana
    SUBSET_SUM = "subset_sum"            # caminho degradado
    BANK = "bank"                        # Passe 4


class MatchStatus(str, Enum):
    MATCHED = "matched"
    WITHIN_TOLERANCE = "matched_within_tolerance"
    DIVERGENT = "divergent"


@dataclass(frozen=True)
class FeeRule(_Cents):
    """platform_fee_rules — contrato por canal, versionado. valid_to é exclusivo."""
    tenant_id: str
    channel: Channel
    commission_bps: int
    commission_base: CommissionBase
    fixed_fee_cents: int
    promo_platform_share_bps: int   # promo_funding_rule: parcela do desconto que cabe à plataforma
    valid_from: date
    valid_to: date | None
    version: int
    refund_reverses_commission: bool = True
    id: str = field(default_factory=new_id)

    def covers(self, d: date) -> bool:
        return self.valid_from <= d and (self.valid_to is None or d < self.valid_to)


@dataclass(frozen=True)
class OrderEvent(_Cents):
    tenant_id: str
    order_id: str
    external_order_ref: str
    channel: Channel
    event_type: EventType          # SALE ou REFUND
    gross_cents: int
    occurred_on: date
    promo_discount_cents: int = 0


@dataclass(frozen=True)
class ExpectedReceivable(_Cents):
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
class SettlementLine(_Cents):
    """settlement_lines (N2)."""
    tenant_id: str
    channel: Channel
    external_order_ref: str | None  # None = relatório agregado (caminho degradado)
    settlement_cycle_id: str
    reported_net_cents: int
    line_type: EventType
    settlement_date: date
    source_hash: str
    raw_payload: dict = field(default_factory=dict, compare=False, hash=False)
    id: str = field(default_factory=new_id)


@dataclass(frozen=True)
class BankTransaction(_Cents):
    """bank_transactions (N3)."""
    tenant_id: str
    amount_cents: int
    value_date: date
    description: str
    source_hash: str
    id: str = field(default_factory=new_id)


@dataclass
class ReconciliationMatch(_Cents):
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
class ReconciliationException(_Cents):
    tenant_id: str
    type: ExceptionType
    amount_cents: int         # positivo = a favor do lojista
    order_ref: str | None
    cycle_id: str | None
    probable_cause: str
    status: ExceptionStatus = ExceptionStatus.OPEN
    match_id: str | None = None
    fingerprint: str = ""
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
    accepted_ip: str
    id: str = field(default_factory=new_id)


class ChargeType(str, Enum):
    PISO = "piso"
    VARIAVEL = "variavel"


class ChargeStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PAID = "paid"
    FAILED = "failed"


@dataclass
class BillingCharge(_Cents):
    tenant_id: str
    charge_type: ChargeType
    period_id: str
    base_amount_cents: int
    computed_amount_cents: int
    cap_applied: bool
    status: ChargeStatus = ChargeStatus.DRAFT
    gateway_ref: str | None = None
    instrument: str | None = None   # single_mandate | subscription | one_off
    ledger_entry_ids: list[str] = field(default_factory=list)
    breakdown: list[dict] = field(default_factory=list)
    id: str = field(default_factory=new_id)
