"""API HTTP do módulo. Rodar: uvicorn conciliacao.api:app --reload

O tenant vem do header X-Tenant-Id apenas para desenvolvimento. Em produção ele DEVE vir de um
claim do token autenticado — header livre é escalonamento horizontal trivial entre lojistas.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .billing import BillingError, BillingService, PricingPlan
from .canonical import SettlementColumnMap, parse_bank_csv, parse_bank_ofx, parse_settlement_csv
from .engine import EngineParams, reconcile
from .fees import CycleCalendar, FeeRuleError, compute_expected
from .gates import Branch, DecisionGateBlocked, DecisionGates, Gate
from .ledger import LedgerError
from .models import (
    AttributionContract, Channel, CommissionBase, EventType, ExceptionStatus, FeeRule, OrderEvent,
)
from .money import fmt_brl
from .store import Store

gates = DecisionGates()
store = Store(gates)
calendar = CycleCalendar()
billing = BillingService(gates, PricingPlan())
params = EngineParams()

app = FastAPI(title="PIZZERIA OS — Conciliação e Cobrança", version="0.1.0")


def now() -> datetime:
    return datetime.now(timezone.utc)


def tenant(x_tenant_id: str = Header(..., alias="X-Tenant-Id")) -> str:
    if not x_tenant_id.strip():
        raise HTTPException(401, "tenant ausente")
    return x_tenant_id.strip()


@app.exception_handler(DecisionGateBlocked)
async def _gate_handler(_, exc: DecisionGateBlocked):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=409, content={"error": "decision_gate_blocked", "gate": exc.gate.value, "detail": str(exc)})


# ---------------------------------------------------------------- gates
class GateIn(BaseModel):
    branch: Branch
    evidence: str
    resolved_on: date


@app.get("/gates")
def get_gates():
    return gates.snapshot()


@app.put("/gates/{gate}")
def resolve_gate(gate: Gate, body: GateIn):
    try:
        gates.resolve(gate, body.branch, body.evidence, body.resolved_on)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return gates.snapshot()[gate.value]


# ---------------------------------------------------------------- N1
class FeeRuleIn(BaseModel):
    channel: Channel
    commission_bps: int = Field(ge=0, le=10_000)
    commission_base: CommissionBase = CommissionBase.GROSS
    fixed_fee_cents: int = Field(ge=0)
    promo_platform_share_bps: int = Field(ge=0, le=10_000)
    valid_from: date
    valid_to: date | None = None
    version: int = Field(ge=1)
    refund_reverses_commission: bool = True


@app.post("/fee-rules", status_code=201)
def add_fee_rule(body: FeeRuleIn, t: str = Depends(tenant)):
    try:
        r = store.fee_rules.add(FeeRule(tenant_id=t, **body.model_dump()))
    except FeeRuleError as e:
        raise HTTPException(422, str(e))
    return {"id": r.id, "version": r.version}


class OrderEventIn(BaseModel):
    order_id: str
    external_order_ref: str
    channel: Channel
    event_type: EventType
    gross_cents: int = Field(ge=0)
    promo_discount_cents: int = Field(default=0, ge=0)
    occurred_on: date


@app.post("/orders/events", status_code=201)
def add_order_events(events: list[OrderEventIn], t: str = Depends(tenant)):
    from .canonical import normalize_ref
    td = store.tenant(t)
    created, skipped = [], 0
    for ev in events:
        key = (ev.order_id, ev.event_type, ev.occurred_on, ev.gross_cents)
        if key in td.order_event_keys:
            skipped += 1
            continue
        oe = OrderEvent(tenant_id=t, **{**ev.model_dump(), "external_order_ref": normalize_ref(ev.external_order_ref)})
        try:
            rule = store.fee_rules.effective(t, oe.channel, oe.occurred_on)
            exp = compute_expected(oe, rule, calendar)
        except FeeRuleError as e:
            raise HTTPException(422, f"{ev.order_id}: {e}")
        store.add_expected(t, exp)
        td.order_event_keys.add(key)
        created += [{"id": x.id, "event_type": x.event_type.value, "expected_net": fmt_brl(x.expected_net_cents),
                     "expected_net_cents": x.expected_net_cents, "cycle_id": x.cycle_id} for x in exp]
    return {"created": created, "duplicates_skipped": skipped}


# ---------------------------------------------------------------- N2 / N3
@app.post("/settlements/{channel}/csv", status_code=201)
async def upload_settlement(channel: Channel, file: UploadFile = File(...), aggregate: bool = False,
                            t: str = Depends(tenant)):
    td = store.tenant(t)
    cols = SettlementColumnMap(order_ref=None) if aggregate else SettlementColumnMap()
    text = (await file.read()).decode("utf-8-sig")
    lines, rep = parse_settlement_csv(t, channel, text, calendar, cols, td.settlement_hashes)
    store.add_settlements(t, lines)
    return rep.__dict__


@app.post("/bank/upload", status_code=201)
async def upload_bank(file: UploadFile = File(...), t: str = Depends(tenant)):
    td = store.tenant(t)
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    parser = parse_bank_ofx if "<OFX" in text.upper() else parse_bank_csv
    txns, rep = parser(t, text, td.bank_hashes)
    store.add_bank(t, txns)
    return rep.__dict__


# ---------------------------------------------------------------- motor
class CloseCyclesIn(BaseModel):
    cycle_ids: list[str]


@app.post("/cycles/close")
def close_cycles(body: CloseCyclesIn, t: str = Depends(tenant)):
    store.tenant(t).closed_cycles.update(body.cycle_ids)
    return {"closed_cycles": sorted(store.tenant(t).closed_cycles)}


@app.post("/reconcile")
def run_reconcile(t: str = Depends(tenant)):
    td = store.tenant(t)
    res = reconcile(t, list(td.expected.values()), list(td.settlements.values()), td.closed_cycles, gates, params)
    td.matches = {m.id: m for m in res.matches}
    new = store.upsert_exceptions(t, res.exceptions, now())
    for exc in new:
        if exc.amount_cents > 0 and exc.status is ExceptionStatus.OPEN:
            td.ledger.detect(exc, now())
    td.reconciled_cycles |= {m.cycle_id for m in res.matches if m.cycle_id in td.closed_cycles}
    return {"metrics": res.metrics, "new_exceptions": len(new), "blocked": res.blocked,
            "pending_expected": len(res.pending_expected), "adjustment_lines": len(res.adjustment_lines)}


@app.get("/exceptions")
def list_exceptions(status: ExceptionStatus | None = None, t: str = Depends(tenant)):
    td = store.tenant(t)
    out = []
    for e in td.exceptions.values():
        if status and e.status is not status:
            continue
        cur = td.ledger.current(e.id)
        out.append({"id": e.id, "type": e.type.value, "amount": fmt_brl(e.amount_cents), "amount_cents": e.amount_cents,
                    "order_ref": e.order_ref, "cycle_id": e.cycle_id, "probable_cause": e.probable_cause,
                    "status": e.status.value, "ledger_state": cur.state.value if cur else None,
                    "history": e.resolution_history})
    return out


# ---------------------------------------------------------------- ledger
class DisputeIn(BaseModel):
    actor: str
    protocol: str


class ConfirmIn(BaseModel):
    amount_cents: int = Field(gt=0)
    attested_by: str
    evidence_ref: str


class RejectIn(BaseModel):
    actor: str
    reason: str


def _exc(t: str, exc_id: str):
    e = store.tenant(t).exceptions.get(exc_id)
    if not e:
        raise HTTPException(404, "exceção não encontrada")
    return e


@app.post("/exceptions/{exc_id}/dispute")
def dispute(exc_id: str, body: DisputeIn, t: str = Depends(tenant)):
    e = _exc(t, exc_id)
    try:
        entry = store.tenant(t).ledger.dispute(e.id, body.actor, now(), body.protocol)
    except LedgerError as err:
        raise HTTPException(409, str(err))
    e.status = ExceptionStatus.IN_RECOVERY
    e.log("disputed", body.actor, now(), protocol=body.protocol)
    return entry.to_dict()


@app.post("/exceptions/{exc_id}/confirm")
def confirm(exc_id: str, body: ConfirmIn, t: str = Depends(tenant)):
    e = _exc(t, exc_id)
    try:
        entry = store.tenant(t).ledger.confirm_manual(e.id, body.amount_cents, body.attested_by, now(), body.evidence_ref)
    except LedgerError as err:
        raise HTTPException(409, str(err))
    e.status = ExceptionStatus.RESOLVED
    e.log("confirmed_manual", body.attested_by, now(), amount_cents=body.amount_cents)
    return entry.to_dict()


@app.post("/exceptions/{exc_id}/reject")
def reject(exc_id: str, body: RejectIn, t: str = Depends(tenant)):
    e = _exc(t, exc_id)
    try:
        entry = store.tenant(t).ledger.reject(e.id, body.actor, now(), body.reason)
    except LedgerError as err:
        raise HTTPException(409, str(err))
    e.status = ExceptionStatus.DISMISSED
    e.log("rejected", body.actor, now(), reason=body.reason)
    return entry.to_dict()


@app.post("/ledger/auto-confirm")
def auto_confirm(t: str = Depends(tenant)):
    """Loop de confirmação automática (Incógnita 1, ramo simplificador). Bloqueado por padrão."""
    gates.require(Gate.IFOOD_TRACEABLE_ADJUSTMENT, "loop de confirmação automática", Branch.SIMPLIFIES)
    td = store.tenant(t)
    adjustments = {}
    for s in td.settlements.values():
        if s.line_type is EventType.ADJUSTMENT and s.external_order_ref:
            adjustments.setdefault(s.external_order_ref, []).append(s)
    confirmed = []
    for e in td.exceptions.values():
        cur = td.ledger.current(e.id)
        if not cur or cur.state.value != "disputed":
            continue
        for adj in adjustments.get(e.order_ref, []):
            try:
                td.ledger.confirm_auto(e.id, adj, e.cycle_id, now())
                e.status = ExceptionStatus.RESOLVED
                e.log("confirmed_auto", "system", now(), adjustment_line_id=adj.id)
                confirmed.append(e.id)
                break
            except LedgerError:
                continue
    return {"confirmed": confirmed}


@app.get("/ledger")
def get_ledger(t: str = Depends(tenant)):
    return [e.to_dict() for e in store.tenant(t).ledger.entries]


@app.get("/ledger/verify")
def verify_ledger(t: str = Depends(tenant)):
    ok, err = store.tenant(t).ledger.verify()
    return {"valid": ok, "error": err}


# ---------------------------------------------------------------- cobrança
class ContractIn(BaseModel):
    terms_version: str
    recovered_definition: str
    accepted_by: str


@app.post("/attribution-contract", status_code=201)
def accept_contract(body: ContractIn, t: str = Depends(tenant)):
    td = store.tenant(t)
    td.contract = AttributionContract(t, now(), body.terms_version, body.recovered_definition, body.accepted_by)
    return {"id": td.contract.id, "accepted_at": td.contract.accepted_at.isoformat()}


def _charge_out(c):
    return {"id": c.id, "type": c.charge_type.value, "period_id": c.period_id, "base": fmt_brl(c.base_amount_cents),
            "computed": fmt_brl(c.computed_amount_cents), "computed_cents": c.computed_amount_cents,
            "cap_applied": c.cap_applied, "status": c.status.value, "breakdown": c.breakdown}


@app.post("/billing/{period_id}/floor")
def floor_charge(period_id: str, t: str = Depends(tenant)):
    c = billing.floor_charge(t, period_id)  # sem gateway configurado: fica em draft
    store.tenant(t).charges[c.id] = c
    return _charge_out(c)


@app.get("/billing/{period_id}/variable/preview")
def variable_preview(period_id: str, t: str = Depends(tenant)):
    td = store.tenant(t)
    c = billing.preview_variable(td.ledger, period_id)
    return {**_charge_out(c), "blockers": billing.variable_readiness(t, td.contract, len(td.reconciled_cycles))
            + ([] if gates.branch(Gate.GATEWAY_VARIABLE_AMOUNT) is not Branch.UNRESOLVED
               else ["Incógnita 2 não resolvida (arquitetura de billing_charge)"])}


@app.exception_handler(BillingError)
async def _billing_handler(_, exc: BillingError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=409, content={"error": "billing_blocked", "detail": str(exc)})
