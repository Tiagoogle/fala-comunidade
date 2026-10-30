"""recovery_ledger — cadeia append-only, encadeada por hash, do valor recuperado.

detected → disputed → confirmed → billed   (e disputed → rejected como terminal)

Regras:
 * nunca há UPDATE/DELETE: cada transição é uma nova entrada com prev_entry_hash;
 * a cadeia é por tenant — apagar uma recuperação inteira também quebra a verificação;
 * confirmed exige disputed antes (a disputa aberta pelo módulo é a base de atribuição);
 * confirmação automática só existe no ramo simplificador da Incógnita 1.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum

from .gates import Branch, DecisionGates, Gate
from .models import EventType, ReconciliationException, SettlementLine, new_id

GENESIS = "0" * 64


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
    prev_entry_hash: str
    entry_hash: str
    seq: int
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["state"] = self.state.value
        d["confirmation_method"] = self.confirmation_method.value if self.confirmation_method else None
        d["state_changed_at"] = self.state_changed_at.isoformat()
        return d


def _hash(payload: dict, prev: str) -> str:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256((prev + body).encode()).hexdigest()


def _payload(tenant_id, exception_id, state, amount, method, basis, actor, at, evidence, seq) -> dict:
    return {
        "tenant_id": tenant_id, "exception_id": exception_id, "state": state.value, "amount_cents": amount,
        "confirmation_method": method.value if method else None, "attribution_basis": basis,
        "actor": actor, "state_changed_at": at.isoformat(), "evidence": evidence, "seq": seq,
    }


class RecoveryLedger:
    def __init__(self, tenant_id: str, gates: DecisionGates) -> None:
        self.tenant_id = tenant_id
        self.gates = gates
        self._entries: list[LedgerEntry] = []

    # ---- leitura -----------------------------------------------------------------------
    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        return tuple(self._entries)

    def history(self, exception_id: str) -> list[LedgerEntry]:
        return [e for e in self._entries if e.exception_id == exception_id]

    def current(self, exception_id: str) -> LedgerEntry | None:
        h = self.history(exception_id)
        return h[-1] if h else None

    def confirmed_unbilled(self) -> list[LedgerEntry]:
        last: dict[str, LedgerEntry] = {}
        for e in self._entries:
            last[e.exception_id] = e
        return [e for e in last.values() if e.state is LedgerState.CONFIRMED]

    def verify(self) -> tuple[bool, str | None]:
        prev = GENESIS
        for i, e in enumerate(self._entries):
            if e.seq != i or e.prev_entry_hash != prev:
                return False, f"cadeia quebrada na posição {i}"
            expected = _hash(_payload(e.tenant_id, e.exception_id, e.state, e.amount_cents, e.confirmation_method,
                                      e.attribution_basis, e.actor, e.state_changed_at, e.evidence, e.seq), prev)
            if expected != e.entry_hash:
                return False, f"entrada {i} adulterada"
            prev = e.entry_hash
        return True, None

    # ---- escrita (append-only) -----------------------------------------------------------
    def _append(self, exception_id: str, state: LedgerState, amount: int, actor: str, at: datetime,
                method: ConfirmationMethod | None = None, basis: str = "", evidence: dict | None = None) -> LedgerEntry:
        cur = self.current(exception_id)
        cur_state = cur.state if cur else None
        if state not in ALLOWED[cur_state]:
            raise LedgerError(f"transição inválida: {cur_state.value if cur_state else '∅'} → {state.value}")
        if cur and at < cur.state_changed_at:
            raise LedgerError("transição com data anterior ao estado vigente")
        if amount <= 0 and state is not LedgerState.REJECTED:
            raise LedgerError("valor de recuperação deve ser positivo")
        if cur and state is not LedgerState.REJECTED and amount > cur.amount_cents:
            raise LedgerError("valor não pode crescer ao longo da cadeia (confirmado ≤ disputado ≤ detectado)")
        evidence = evidence or {}
        seq = len(self._entries)
        prev = self._entries[-1].entry_hash if self._entries else GENESIS
        basis = basis or (cur.attribution_basis if cur else "")
        h = _hash(_payload(self.tenant_id, exception_id, state, amount, method, basis, actor, at, evidence, seq), prev)
        entry = LedgerEntry(self.tenant_id, exception_id, state, amount, method, basis, actor, at,
                            evidence, prev, h, seq)
        self._entries.append(entry)
        return entry

    def detect(self, exc: ReconciliationException, at: datetime) -> LedgerEntry:
        if exc.tenant_id != self.tenant_id:
            raise PermissionError("exceção de outro tenant")
        if exc.amount_cents <= 0:
            raise LedgerError("exceção sem valor recuperável a favor do lojista")
        return self._append(exc.id, LedgerState.DETECTED, exc.amount_cents, "system", at,
                            basis=f"detectado pelo motor: {exc.type.value}",
                            evidence={"type": exc.type.value, "order_ref": exc.order_ref, "cycle_id": exc.cycle_id,
                                      "probable_cause": exc.probable_cause})

    def dispute(self, exception_id: str, actor: str, at: datetime, protocol: str) -> LedgerEntry:
        cur = self.current(exception_id)
        if not cur:
            raise LedgerError("exceção não registrada no ledger")
        return self._append(exception_id, LedgerState.DISPUTED, cur.amount_cents, actor, at,
                            basis="disputa aberta pelo módulo junto à plataforma",
                            evidence={"dispute_protocol": protocol})

    def confirm_manual(self, exception_id: str, amount: int, attested_by: str, at: datetime,
                       evidence_ref: str) -> LedgerEntry:
        """Atestação do lojista (ou prova pela conciliação bancária). Funciona em qualquer ramo da Incógnita 1."""
        if not evidence_ref:
            raise LedgerError("confirmação manual exige referência de evidência (comprovante, extrato, protocolo)")
        return self._append(exception_id, LedgerState.CONFIRMED, amount, attested_by, at,
                            method=ConfirmationMethod.MANUAL, evidence={"evidence_ref": evidence_ref})

    def confirm_auto(self, exception_id: str, adjustment: SettlementLine, original_cycle_id: str | None,
                     at: datetime) -> LedgerEntry:
        """Fecha a cadeia sozinho ao ver o ajuste rastreável num ciclo posterior. Só no ramo simplificador."""
        self.gates.require(Gate.IFOOD_TRACEABLE_ADJUSTMENT, "confirmação automática de recuperação",
                           branch=Branch.SIMPLIFIES)
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
        amount = min(adjustment.reported_net_cents, cur.amount_cents)
        return self._append(exception_id, LedgerState.CONFIRMED, amount, "system", at,
                            method=ConfirmationMethod.AUTO,
                            evidence={"adjustment_line_id": adjustment.id, "adjustment_hash": adjustment.source_hash,
                                      "settlement_cycle_id": adjustment.settlement_cycle_id})

    def reject(self, exception_id: str, actor: str, at: datetime, reason: str) -> LedgerEntry:
        return self._append(exception_id, LedgerState.REJECTED, 0, actor, at, evidence={"reason": reason})

    def mark_billed(self, exception_id: str, charge_id: str, at: datetime) -> LedgerEntry:
        cur = self.current(exception_id)
        if not cur:
            raise LedgerError("exceção não registrada no ledger")
        return self._append(exception_id, LedgerState.BILLED, cur.amount_cents, "billing", at,
                            method=cur.confirmation_method, evidence={"charge_id": charge_id})
