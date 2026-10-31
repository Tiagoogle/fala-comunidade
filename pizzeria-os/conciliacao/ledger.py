"""RecoveryLedgerService — cadeia append-only do valor recuperado (Prompt Mestre §7).

    detected → disputed → confirmed → billed      (+ disputed → rejected, terminal)

Decisão de projeto (ADR-001 §4): a cadeia de hash é POR TENANT, não por exceção. Uma cadeia por
exceção detecta adulteração dentro da recuperação, mas não detecta a exclusão de uma recuperação
inteira (a cadeia some junto). Encadeando todas as entradas do tenant, apagar qualquer coisa quebra
a verificação. verify_chain(exception_id) continua disponível: valida a cadeia inteira e confirma
que as entradas da exceção estão nela, em ordem.

A primeira entrada do tenant tem prev_entry_hash = None (§7.2).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum

from .flags import Flag, FlagService
from .models import EventType, ReconciliationException, SettlementLine, check_cents, new_id


class LedgerState(str, Enum):
    DETECTED = "detected"
    DISPUTED = "disputed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    BILLED = "billed"


class ConfirmationMethod(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"


ALLOWED = {
    None: {LedgerState.DETECTED},
    LedgerState.DETECTED: {LedgerState.DISPUTED},
    LedgerState.DISPUTED: {LedgerState.CONFIRMED, LedgerState.REJECTED},
    LedgerState.CONFIRMED: {LedgerState.BILLED},
    LedgerState.REJECTED: set(),
    LedgerState.BILLED: set(),
}


class LedgerError(ValueError):
    pass


class ConfirmationModeError(LedgerError):
    pass


@dataclass(frozen=True)
class LedgerEntry:
    tenant_id: str
    exception_id: str
    state: LedgerState
    amount_cents: int
    confirmation_method: ConfirmationMethod | None
    attribution_basis: str
    actor: str
    state_changed_at: datetime
    evidence: dict
    prev_entry_hash: str | None
    entry_hash: str
    seq: int
    id: str = field(default_factory=new_id)

    def __post_init__(self):
        check_cents(self)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["state"] = self.state.value
        d["confirmation_method"] = self.confirmation_method.value if self.confirmation_method else None
        d["state_changed_at"] = self.state_changed_at.isoformat()
        return d


def _canonical(e: dict) -> str:
    return json.dumps(e, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _hash(tenant_id, exception_id, state, amount, method, basis, actor, at, evidence, seq, prev) -> str:
    payload = {
        "tenant_id": tenant_id, "exception_id": exception_id, "state": state.value, "amount_cents": amount,
        "confirmation_method": method.value if method else None, "attribution_basis": basis, "actor": actor,
        "state_changed_at": at.isoformat(), "evidence": evidence, "seq": seq, "prev_entry_hash": prev,
    }
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()


class RecoveryLedgerService:
    def __init__(self, tenant_id: str, flags: FlagService) -> None:
        self.tenant_id = tenant_id
        self.flags = flags
        self._entries: list[LedgerEntry] = []

    # ------------------------------------------------------------------ leitura
    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        return tuple(self._entries)

    def history(self, exception_id: str) -> list[LedgerEntry]:
        return [e for e in self._entries if e.exception_id == exception_id]

    def current(self, exception_id: str) -> LedgerEntry | None:
        h = self.history(exception_id)
        return h[-1] if h else None

    def latest_by_exception(self) -> dict[str, LedgerEntry]:
        last: dict[str, LedgerEntry] = {}
        for e in self._entries:
            last[e.exception_id] = e
        return last

    def confirmed_unbilled(self, until: datetime | None = None) -> list[LedgerEntry]:
        return [e for e in self.latest_by_exception().values()
                if e.state is LedgerState.CONFIRMED and (until is None or e.state_changed_at < until)]

    def count_confirmed(self) -> int:
        return sum(1 for e in self._entries if e.state is LedgerState.CONFIRMED)

    def verify_chain(self, exception_id: str | None = None) -> bool:
        prev = None
        positions = []
        for i, e in enumerate(self._entries):
            if e.seq != i or e.prev_entry_hash != prev or e.tenant_id != self.tenant_id:
                return False
            if _hash(e.tenant_id, e.exception_id, e.state, e.amount_cents, e.confirmation_method, e.attribution_basis,
                     e.actor, e.state_changed_at, e.evidence, e.seq, e.prev_entry_hash) != e.entry_hash:
                return False
            if exception_id is not None and e.exception_id == exception_id:
                positions.append(e)
            prev = e.entry_hash
        if exception_id is not None:
            states = [e.state for e in positions]
            cur = None
            for s in states:  # a sequência de estados da exceção precisa ser uma trajetória válida
                if s not in ALLOWED[cur]:
                    return False
                cur = s
        return True

    # ------------------------------------------------------------------ escrita
    def append_entry(self, exception_id: str, new_state: LedgerState, amount_cents: int, *, actor: str,
                     at: datetime, confirmation_method: ConfirmationMethod | None = None,
                     attribution_basis: str = "", evidence: dict | None = None) -> LedgerEntry:
        """Único ponto de escrita. INSERT only — não existe método de update/delete."""
        cur = self.current(exception_id)
        cur_state = cur.state if cur else None
        if new_state not in ALLOWED[cur_state]:
            raise LedgerError(f"transição inválida: {cur_state.value if cur_state else '∅'} → {new_state.value}")
        if cur and at < cur.state_changed_at:
            raise LedgerError("transição com data anterior ao estado vigente")
        if type(amount_cents) is not int:
            raise LedgerError("amount_cents deve ser int")
        if new_state is not LedgerState.REJECTED and amount_cents <= 0:
            raise LedgerError("valor de recuperação deve ser positivo")
        if cur and new_state is not LedgerState.REJECTED and amount_cents > cur.amount_cents:
            raise LedgerError("valor não pode crescer ao longo da cadeia (confirmado ≤ disputado ≤ detectado)")
        if new_state is LedgerState.CONFIRMED and confirmation_method is None:
            raise LedgerError("confirmed exige confirmation_method")
        evidence = evidence or {}
        basis = attribution_basis or (cur.attribution_basis if cur else "")
        seq = len(self._entries)
        prev = self._entries[-1].entry_hash if self._entries else None
        h = _hash(self.tenant_id, exception_id, new_state, amount_cents, confirmation_method, basis, actor, at,
                  evidence, seq, prev)
        entry = LedgerEntry(self.tenant_id, exception_id, new_state, amount_cents, confirmation_method, basis,
                            actor, at, evidence, prev, h, seq)
        self._entries.append(entry)
        return entry

    def transition(self, exception_id: str, new_state: LedgerState, *, actor: str, at: datetime,
                   amount_cents: int | None = None, **kw) -> LedgerEntry:
        cur = self.current(exception_id)
        if cur is None:
            raise LedgerError("exceção não registrada no ledger")
        amount = cur.amount_cents if amount_cents is None else amount_cents
        return self.append_entry(exception_id, new_state, amount, actor=actor, at=at, **kw)

    # ------------------------------------------------------------------ operações de domínio
    def detect(self, exc: ReconciliationException, at: datetime) -> LedgerEntry:
        if exc.tenant_id != self.tenant_id:
            raise PermissionError("exceção de outro tenant")
        if exc.amount_cents <= 0:
            raise LedgerError("exceção sem valor recuperável a favor do lojista")
        return self.append_entry(exc.id, LedgerState.DETECTED, exc.amount_cents, actor="system", at=at,
                                 attribution_basis=f"detectado pelo motor: {exc.type.value}",
                                 evidence={"type": exc.type.value, "order_ref": exc.order_ref,
                                           "cycle_id": exc.cycle_id, "probable_cause": exc.probable_cause})

    def dispute(self, exception_id: str, actor: str, at: datetime, protocol: str) -> LedgerEntry:
        return self.transition(exception_id, LedgerState.DISPUTED, actor=actor, at=at,
                               attribution_basis="disputa aberta pelo módulo junto à plataforma",
                               evidence={"dispute_protocol": protocol})

    def confirm_manual(self, exception_id: str, amount_cents: int, attested_by: str, at: datetime,
                       evidence_ref: str) -> LedgerEntry:
        """Ramo encarecedor da Incógnita 1: atestação do lojista ou prova bancária."""
        if self.flags.is_on(self.tenant_id, Flag.CONFIRMATION_METHOD_AUTO):
            raise ConfirmationModeError("tenant em confirmação automática; atestação manual desabilitada")
        if not evidence_ref:
            raise LedgerError("atestação manual exige referência de evidência")
        return self.transition(exception_id, LedgerState.CONFIRMED, actor=attested_by, at=at,
                               amount_cents=amount_cents, confirmation_method=ConfirmationMethod.MANUAL,
                               evidence={"evidence_ref": evidence_ref})

    def confirm_auto(self, exception_id: str, adjustment: SettlementLine, original_cycle_id: str | None,
                     at: datetime) -> LedgerEntry:
        """Ramo simplificador da Incógnita 1: ajuste rastreável em ciclo posterior fecha a cadeia."""
        if not self.flags.is_on(self.tenant_id, Flag.CONFIRMATION_METHOD_AUTO):
            raise ConfirmationModeError("confirmation_method_auto=false para o tenant")
        cur = self.current(exception_id)
        if not cur or cur.state is not LedgerState.DISPUTED:
            raise LedgerError("confirmação automática exige estado disputed")
        if adjustment.tenant_id != self.tenant_id or adjustment.line_type is not EventType.ADJUSTMENT:
            raise LedgerError("linha não é um ajuste deste tenant")
        if adjustment.external_order_ref != self.history(exception_id)[0].evidence.get("order_ref"):
            raise LedgerError("ajuste não referencia o pedido em disputa")
        if original_cycle_id and adjustment.settlement_cycle_id <= original_cycle_id:
            raise LedgerError("ajuste deve ser liquidado em ciclo posterior ao original")
        if adjustment.reported_net_cents <= 0:
            raise LedgerError("ajuste não credita o lojista")
        return self.transition(exception_id, LedgerState.CONFIRMED, actor="system", at=at,
                               amount_cents=min(adjustment.reported_net_cents, cur.amount_cents),
                               confirmation_method=ConfirmationMethod.AUTO,
                               evidence={"adjustment_line_id": adjustment.id, "adjustment_hash": adjustment.source_hash,
                                         "settlement_cycle_id": adjustment.settlement_cycle_id})

    def reject(self, exception_id: str, actor: str, at: datetime, reason: str) -> LedgerEntry:
        return self.transition(exception_id, LedgerState.REJECTED, actor=actor, at=at, amount_cents=0,
                               evidence={"reason": reason})

    def mark_billed(self, exception_id: str, charge_id: str, at: datetime) -> LedgerEntry:
        cur = self.current(exception_id)
        return self.transition(exception_id, LedgerState.BILLED, actor="billing", at=at,
                               confirmation_method=cur.confirmation_method if cur else None,
                               evidence={"charge_id": charge_id})
