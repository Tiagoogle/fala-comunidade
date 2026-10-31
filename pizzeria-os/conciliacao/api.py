"""API HTTP. Rodar: uvicorn conciliacao.api:app --reload  ·  dashboard em /dashboard

Autenticação (DEV ONLY): tenant em X-Tenant-Id e admin em X-Admin-Token == PIZZERIA_ADMIN_TOKEN.
Em produção o tenant DEVE vir de claim do JWT — header livre permite acesso cruzado entre lojistas.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, StrictInt

from .billing import BillingError
from .canonical import SettlementColumnMap
from .fees import FeeRuleError
from .flags import Flag
from .ledger import LedgerError
from .models import Channel, CommissionBase, EventType, ExceptionStatus
from .money import fmt_brl
from .onboarding import DEFAULT_RECOVERED_DEFINITION, OnboardingError
from .service import ConciliacaoApp
from .store import TenantIsolationError

svc = ConciliacaoApp()
app = FastAPI(title="PIZZERIA OS — Conciliação e Cobrança", version="0.2.0")
ADMIN_TOKEN = os.environ.get("PIZZERIA_ADMIN_TOKEN", "dev-admin")


_ERROR_STATUS = [
    (TenantIsolationError, 403), (OnboardingError, 409), (BillingError, 409), (LedgerError, 409),
    (FeeRuleError, 422), (LookupError, 404), (ValueError, 422), (TypeError, 422),
]


async def _domain_error(_: Request, exc: Exception):
    # Mais específico primeiro (ex.: LedgerError é ValueError) — a ordem da tabela decide o status.
    code = next(c for cls, c in _ERROR_STATUS if isinstance(exc, cls))
    return JSONResponse(status_code=code, content={"error": type(exc).__name__, "detail": str(exc)})


for _cls, _ in _ERROR_STATUS:
    app.add_exception_handler(_cls, _domain_error)


def tenant(x_tenant_id: str = Header(..., alias="X-Tenant-Id")) -> str:
    t = x_tenant_id.strip()
    if not svc.store.exists(t):
        raise HTTPException(404, "tenant inexistente")
    return t


def admin(x_admin_token: str = Header(..., alias="X-Admin-Token")) -> str:
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(403, "admin token inválido")
    return "admin"


# ---------------------------------------------------------------- onboarding
class RegisterIn(BaseModel):
    tenant_id: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9-]+$")
    name: str
    cnpj: str
    address: str
    legal_representative: str
    contact_email: str


@app.post("/onboarding/register", status_code=201)
def register(body: RegisterIn):
    td = svc.register_tenant(**body.model_dump())
    return {"tenant_id": td.profile.tenant_id, "next_step": td.onboarding.next_step}


class FeeContractIn(BaseModel):
    channel: Channel = Channel.IFOOD
    commission_bps: StrictInt = Field(ge=0, le=10_000)
    commission_base: CommissionBase = CommissionBase.GROSS
    fixed_fee_cents: StrictInt = Field(ge=0)
    promo_platform_share_bps: StrictInt = Field(ge=0, le=10_000)
    onboarding_date: date | None = None


@app.post("/onboarding/fee-contract")
def fee_contract(body: FeeContractIn, t: str = Depends(tenant)):
    r = svc.configure_fee_contract(t, **body.model_dump())
    return {"rule_id": r.id, "version": r.version, "valid_from": r.valid_from}


class AttributionIn(BaseModel):
    terms_version: str
    accepted_by: str
    recovered_definition: str = DEFAULT_RECOVERED_DEFINITION


@app.post("/onboarding/attribution")
def attribution(body: AttributionIn, request: Request, t: str = Depends(tenant)):
    c = svc.accept_attribution(t, body.terms_version, body.recovered_definition, body.accepted_by,
                               request.client.host if request.client else "unknown")
    return {"contract_id": c.id, "accepted_at": c.accepted_at}


class IntegrationsIn(BaseModel):
    ifood_token: str
    mercadopago_token: str


@app.post("/onboarding/integrations")
def integrations(body: IntegrationsIn, t: str = Depends(tenant)):
    svc.connect_integrations(t, body.ifood_token, body.mercadopago_token)
    return {"next_step": svc.store.tenant(t).onboarding.next_step}


class CalibrationIn(BaseModel):
    approve: bool
    actor: str


@app.post("/onboarding/calibrate")
def calibrate(body: CalibrationIn, t: str = Depends(tenant)):
    summary = svc.calibrate(t, body.approve, body.actor)
    return {"summary": summary, "active": svc.store.tenant(t).onboarding.active}


@app.get("/onboarding/state")
def onboarding_state(t: str = Depends(tenant)):
    o = svc.store.tenant(t).onboarding
    return {"next_step": o.next_step, "active": o.active, "history": o.history,
            "calibration": o.calibration_summary}


# ---------------------------------------------------------------- admin: flags
class FlagIn(BaseModel):
    value: bool
    changed_by: str
    evidence: str


@app.put("/admin/tenants/{tenant_id}/flags/{flag}")
def set_flag(tenant_id: str, flag: Flag, body: FlagIn, _: str = Depends(admin)):
    svc.flags.set(tenant_id, flag, body.value, body.changed_by, body.evidence, datetime.now())
    return svc.flags.snapshot(tenant_id)


@app.get("/admin/tenants/{tenant_id}/flags")
def get_flags(tenant_id: str, _: str = Depends(admin)):
    return {"flags": svc.flags.snapshot(tenant_id),
            "audit": [{**a.__dict__, "flag": a.flag.value, "changed_at": a.changed_at.isoformat()}
                      for a in svc.flags.audit(tenant_id)]}


# ---------------------------------------------------------------- ingestão
class OrderEventIn(BaseModel):
    order_id: str
    external_order_ref: str
    channel: Channel
    event_type: EventType
    gross_cents: StrictInt = Field(ge=0)          # INV-1: StrictInt rejeita 68.9
    promo_discount_cents: StrictInt = Field(default=0, ge=0)
    occurred_on: date


@app.post("/orders/events", status_code=201)
def order_events(events: list[OrderEventIn], t: str = Depends(tenant)):
    created = svc.add_order_events(t, [e.model_dump() for e in events])
    return [{"id": x.id, "event_type": x.event_type.value, "expected_net_cents": x.expected_net_cents,
             "cycle_id": x.cycle_id} for x in created]


@app.post("/settlements/{channel}/csv", status_code=201)
async def settlements(channel: Channel, file: UploadFile = File(...), aggregate: bool = False,
                      t: str = Depends(tenant)):
    cols = SettlementColumnMap(order_ref=None) if aggregate else None
    return svc.ingest_settlement(t, channel, (await file.read()).decode("utf-8-sig"), cols).__dict__


@app.post("/bank/upload", status_code=201)
async def bank(file: UploadFile = File(...), t: str = Depends(tenant)):
    return svc.ingest_bank(t, (await file.read()).decode("utf-8-sig", errors="replace")).__dict__


class CyclesIn(BaseModel):
    cycle_ids: list[str]


@app.post("/cycles/close")
def close(body: CyclesIn, t: str = Depends(tenant)):
    svc.close_cycles(t, body.cycle_ids)
    return {"closed": sorted(svc.store.tenant(t).closed_cycles)}


# ---------------------------------------------------------------- motor / ledger
@app.post("/reconcile")
def reconcile(cycle_id: str | None = None, t: str = Depends(tenant)):
    res = svc.reconcile(t, cycle_id)
    return {"metrics": res.metrics, "warnings": res.warnings, "pending_expected": len(res.pending_expected)}


@app.post("/jobs/drain")
def drain(_: str = Depends(admin)):
    """Dev: executa o worker em processo. Produção: worker RQ separado."""
    return {"executed": svc.queue.drain()}


@app.get("/exceptions")
def exceptions(status: ExceptionStatus | None = None, t: str = Depends(tenant)):
    td = svc.store.tenant(t)
    out = []
    for e in td.exceptions.values():
        if status and e.status is not status:
            continue
        cur = td.ledger.current(e.id)
        out.append({"id": e.id, "type": e.type.value, "amount": fmt_brl(e.amount_cents), "amount_cents": e.amount_cents,
                    "order_ref": e.order_ref, "cycle_id": e.cycle_id, "probable_cause": e.probable_cause,
                    "status": e.status.value, "ledger_state": cur.state.value if cur else None})
    return out


@app.get("/exceptions/{exc_id}/trail")
def trail(exc_id: str, t: str = Depends(tenant)):
    td = svc.store.tenant(t)
    e = svc._exc(t, exc_id)
    return {"exception": {"id": e.id, "history": e.resolution_history},
            "ledger": [x.to_dict() for x in td.ledger.history(e.id)],
            "chain_valid": td.ledger.verify_chain(e.id)}


class DisputeIn(BaseModel):
    actor: str
    protocol: str


class ConfirmIn(BaseModel):
    amount_cents: StrictInt = Field(gt=0)
    attested_by: str
    evidence_ref: str


class RejectIn(BaseModel):
    actor: str
    reason: str


@app.post("/exceptions/{exc_id}/dispute")
def dispute(exc_id: str, body: DisputeIn, t: str = Depends(tenant)):
    return svc.dispute(t, exc_id, body.actor, body.protocol).to_dict()


@app.post("/exceptions/{exc_id}/confirm")
def confirm(exc_id: str, body: ConfirmIn, t: str = Depends(tenant)):
    return svc.confirm_manual(t, exc_id, body.amount_cents, body.attested_by, body.evidence_ref).to_dict()


@app.post("/exceptions/{exc_id}/reject")
def reject(exc_id: str, body: RejectIn, t: str = Depends(tenant)):
    return svc.reject(t, exc_id, body.actor, body.reason).to_dict()


@app.post("/ledger/confirmation-loop")
def confirmation_loop(t: str = Depends(tenant)):
    return {"confirmed": svc.run_confirmation_loop(t),
            "mode": "auto" if svc.flags.is_on(t, Flag.CONFIRMATION_METHOD_AUTO) else "manual"}


@app.get("/ledger/verify")
def verify(t: str = Depends(tenant)):
    return {"valid": svc.store.tenant(t).ledger.verify_chain()}


# ---------------------------------------------------------------- cobrança
def _charge(c):
    return {"id": c.id, "type": c.charge_type.value, "period_id": c.period_id, "base_cents": c.base_amount_cents,
            "computed_cents": c.computed_amount_cents, "cap_applied": c.cap_applied, "status": c.status.value,
            "instrument": c.instrument, "breakdown": c.breakdown}


@app.post("/billing/{period_id}/piso")
def piso(period_id: str, t: str = Depends(tenant)):
    return _charge(svc.emit_floor(t, period_id))  # sem gateway configurado: draft


@app.get("/billing/{period_id}/variavel/preview")
def variavel_preview(period_id: str, t: str = Depends(tenant)):
    td = svc.store.tenant(t)
    c = svc.billing.preview_variable(td.ledger, period_id)
    return {**_charge(c), "blockers": svc.billing.variable_blockers(svc.billing_context(t), td.ledger)}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return (Path(__file__).parent / "static" / "dashboard.html").read_text(encoding="utf-8")
