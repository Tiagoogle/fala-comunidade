"""Camada de aplicação: orquestra onboarding, ingestão, motor, ledger e cobrança por tenant."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from .billing import BillingService, PricingPlan, TenantBillingContext
from .canonical import (
    SettlementColumnMap, normalize_ref, parse_bank_csv, parse_bank_ofx, parse_settlement_csv,
)
from .engine import EngineInput, EngineParams, ReconciliationEngine, RunResult
from .fees import CycleCalendar, compute_expected
from .flags import Flag, FlagService
from .gateways.mercadopago import BillingGateway
from .integrations import IntegrationTokenStore
from .jobs import InMemoryJobQueue, JobQueue
from .ledger import LedgerState
from .models import (
    Channel, ChargeType, EventType, ExceptionStatus, OrderEvent, RECOVERABLE_TYPES,
)
from .onboarding import (
    OnboardingError, Step, TenantProfile, make_contract, make_fee_rule, valid_cnpj,
)
from .store import Store
from .subset_sum import solve

SUBSET_JOB = "subset_sum"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ConciliacaoApp:
    flags: FlagService = field(default_factory=FlagService)
    calendar: CycleCalendar = field(default_factory=CycleCalendar)
    params: EngineParams = field(default_factory=EngineParams)
    plan: PricingPlan = field(default_factory=PricingPlan)
    queue: JobQueue = field(default_factory=InMemoryJobQueue)
    tokens: IntegrationTokenStore = field(default_factory=IntegrationTokenStore)
    clock: callable = utcnow

    def __post_init__(self):
        self.store = Store(self.flags)
        self.engine = ReconciliationEngine(self.calendar, self.params)
        self.billing = BillingService(self.flags, self.plan)

    # ============================================================ onboarding
    def register_tenant(self, tenant_id: str, name: str, cnpj: str, address: str, legal_representative: str,
                        contact_email: str):
        if not valid_cnpj(cnpj):
            raise OnboardingError("CNPJ inválido")
        if "@" not in contact_email:
            raise OnboardingError("e-mail inválido")
        td = self.store.create_tenant(TenantProfile(tenant_id, name, cnpj, address, legal_representative,
                                                    contact_email, self.clock()))
        td.onboarding.complete(Step.TENANT_REGISTERED, self.clock())
        return td

    def configure_fee_contract(self, tenant_id: str, channel: Channel, commission_bps: int, commission_base,
                               fixed_fee_cents: int, promo_platform_share_bps: int, onboarding_date: date | None = None):
        td = self.store.tenant(tenant_id)
        td.onboarding.require(Step.FEE_CONTRACT)
        rule = make_fee_rule(tenant_id, onboarding_date or self.clock().date(), channel, commission_bps,
                             commission_base, fixed_fee_cents, promo_platform_share_bps)
        self.store.fee_rules.add(rule)
        td.onboarding.complete(Step.FEE_CONTRACT, self.clock(), rule_id=rule.id)
        return rule

    def accept_attribution(self, tenant_id: str, terms_version: str, recovered_definition: str, accepted_by: str,
                           accepted_ip: str):
        td = self.store.tenant(tenant_id)
        td.onboarding.require(Step.ATTRIBUTION_ACCEPTED)
        td.contract = make_contract(tenant_id, terms_version, recovered_definition, accepted_by, accepted_ip, self.clock())
        td.onboarding.complete(Step.ATTRIBUTION_ACCEPTED, self.clock(), terms_version=terms_version)
        return td.contract

    def connect_integrations(self, tenant_id: str, ifood_token: str, mercadopago_token: str,
                             expires_at: datetime | None = None):
        td = self.store.tenant(tenant_id)
        if td.contract is None:
            raise OnboardingError("PROIBIDO conectar integrações sem attribution_contract aceito")
        td.onboarding.require(Step.INTEGRATIONS_CONNECTED)
        self.tokens.put(tenant_id, "ifood", ifood_token, None, expires_at)
        self.tokens.put(tenant_id, "mercadopago", mercadopago_token, None, expires_at)
        td.onboarding.complete(Step.INTEGRATIONS_CONNECTED, self.clock())

    def calibrate(self, tenant_id: str, approve: bool, actor: str) -> dict:
        """Etapa 5: roda o motor em modo calibração sobre o primeiro ciclo já carregado.
        Produz matches/exceções para o lojista revisar; NÃO cria ledger nem cobrança."""
        td = self.store.tenant(tenant_id)
        td.onboarding.require(Step.CALIBRATION_DONE)
        res = self.reconcile(tenant_id, calibration=True)
        summary = {"metrics": res.metrics, "warnings": res.warnings}
        td.onboarding.calibration_summary = summary
        if approve:
            td.onboarding.complete(Step.CALIBRATION_DONE, self.clock(), approved_by=actor)
        return summary

    # ============================================================ ingestão
    def add_order_events(self, tenant_id: str, events: list[dict]) -> list:
        td = self.store.tenant(tenant_id)
        created = []
        for ev in events:
            key = (ev["order_id"], ev["event_type"], ev["occurred_on"], ev["gross_cents"])
            if key in td.order_event_keys:
                continue
            oe = OrderEvent(tenant_id, ev["order_id"], normalize_ref(ev["external_order_ref"]), Channel(ev["channel"]),
                            EventType(ev["event_type"]), ev["gross_cents"], ev["occurred_on"],
                            ev.get("promo_discount_cents", 0))
            rule = self.store.fee_rules.effective(tenant_id, oe.channel, oe.occurred_on)  # INV-5: data do evento
            exp = compute_expected(oe, rule, self.calendar)
            self.store.check(tenant_id, exp)
            for x in exp:
                td.expected[x.id] = x
            td.order_event_keys.add(key)
            created.extend(exp)
        return created

    def ingest_settlement(self, tenant_id: str, channel: Channel, text: str, columns: SettlementColumnMap | None = None):
        td = self.store.tenant(tenant_id)
        lines, rep = parse_settlement_csv(tenant_id, channel, text, self.calendar, columns, td.settlement_hashes)
        self.store.check(tenant_id, lines)
        for s in lines:
            td.settlements[s.id] = s
        return rep

    def ingest_bank(self, tenant_id: str, text: str):
        td = self.store.tenant(tenant_id)
        parser = parse_bank_ofx if "<OFX" in text.upper() else parse_bank_csv
        txns, rep = parser(tenant_id, text, td.bank_hashes)
        self.store.check(tenant_id, txns)
        for b in txns:
            td.bank[b.id] = b
        return rep

    def close_cycles(self, tenant_id: str, cycle_ids: list[str]) -> None:
        self.store.tenant(tenant_id).closed_cycles.update(cycle_ids)

    # ============================================================ motor
    def _engine_input(self, tenant_id: str) -> EngineInput:
        td = self.store.tenant(tenant_id)
        return EngineInput(tenant_id, list(td.expected.values()), list(td.settlements.values()), list(td.bank.values()),
                           set(td.closed_cycles), self.flags.is_on(tenant_id, Flag.SETTLEMENT_ITEMIZED),
                           dict(td.subset_results),
                           {k.split("|", 1)[1] for k in self.queue.pending(SUBSET_JOB) if k.startswith(tenant_id + "|")})

    def reconcile(self, tenant_id: str, cycle_id: str | None = None, calibration: bool = False) -> RunResult:
        td = self.store.tenant(tenant_id)
        if not calibration and not td.onboarding.active:
            raise OnboardingError(f"tenant em onboarding (próxima etapa: {td.onboarding.next_step.name})")
        inp = self._engine_input(tenant_id)
        res = self.engine.run(inp, cycle_id)
        for line in res.subset_sum_requests:
            self._enqueue_subset(tenant_id, line.id)
        if calibration:
            return res
        td.matches.update({m.id: m for m in res.matches})
        now = self.clock()
        for exc in res.exceptions:
            existing = td.exceptions_by_fp.get(exc.fingerprint)
            if existing:
                cur = td.exceptions[existing]
                if cur.amount_cents != exc.amount_cents:
                    cur.log("amount_revised", "engine", now, old=cur.amount_cents, new=exc.amount_cents)
                    cur.amount_cents = exc.amount_cents
                continue
            exc.log("created", "engine", now)
            td.exceptions[exc.id] = exc
            td.exceptions_by_fp[exc.fingerprint] = exc.id
            if exc.status is ExceptionStatus.OPEN and exc.amount_cents > 0 and exc.type in RECOVERABLE_TYPES:
                td.ledger.detect(exc, now)
        td.reconciled_cycles |= {m.cycle_id for m in res.matches if m.cycle_id in td.closed_cycles}
        return res

    def _enqueue_subset(self, tenant_id: str, line_id: str) -> None:
        def job():
            td = self.store.tenant(tenant_id)
            line = td.settlements[line_id]
            candidates = self.engine.subset_sum_candidates(self._engine_input(tenant_id), line)
            td.subset_results[line_id] = solve(line.reported_net_cents, candidates, self.params.subset_sum_tolerance_cents)
        self.queue.enqueue(SUBSET_JOB, f"{tenant_id}|{line_id}", job)

    # ============================================================ ledger
    def _exc(self, tenant_id: str, exc_id: str):
        e = self.store.tenant(tenant_id).exceptions.get(exc_id)
        if e is None:
            raise LookupError("exceção não encontrada")
        return e

    def dispute(self, tenant_id, exc_id, actor, protocol):
        e = self._exc(tenant_id, exc_id)
        entry = self.store.tenant(tenant_id).ledger.dispute(e.id, actor, self.clock(), protocol)
        e.status = ExceptionStatus.IN_RECOVERY
        e.log("disputed", actor, self.clock(), protocol=protocol)
        return entry

    def confirm_manual(self, tenant_id, exc_id, amount_cents, attested_by, evidence_ref):
        e = self._exc(tenant_id, exc_id)
        entry = self.store.tenant(tenant_id).ledger.confirm_manual(e.id, amount_cents, attested_by, self.clock(), evidence_ref)
        e.status = ExceptionStatus.RESOLVED
        e.log("confirmed_manual", attested_by, self.clock(), amount_cents=amount_cents)
        return entry

    def reject(self, tenant_id, exc_id, actor, reason):
        e = self._exc(tenant_id, exc_id)
        entry = self.store.tenant(tenant_id).ledger.reject(e.id, actor, self.clock(), reason)
        e.status = ExceptionStatus.DISMISSED
        e.log("rejected", actor, self.clock(), reason=reason)
        return entry

    def run_confirmation_loop(self, tenant_id: str) -> list[str]:
        """Loop automático (Incógnita 1, ramo simplificador). No-op se a flag estiver desligada."""
        if not self.flags.is_on(tenant_id, Flag.CONFIRMATION_METHOD_AUTO):
            return []
        td = self.store.tenant(tenant_id)
        adjustments: dict[str, list] = {}
        for s in td.settlements.values():
            if s.line_type is EventType.ADJUSTMENT and s.external_order_ref:
                adjustments.setdefault(s.external_order_ref, []).append(s)
        used = {e.evidence.get("adjustment_line_id") for e in td.ledger.entries}
        confirmed = []
        for e in td.exceptions.values():
            cur = td.ledger.current(e.id)
            if not cur or cur.state is not LedgerState.DISPUTED:
                continue
            for adj in sorted(adjustments.get(e.order_ref, []), key=lambda a: a.settlement_date):
                if adj.id in used:
                    continue
                try:
                    td.ledger.confirm_auto(e.id, adj, e.cycle_id, self.clock())
                except ValueError:
                    continue
                used.add(adj.id)
                e.status = ExceptionStatus.RESOLVED
                e.log("confirmed_auto", "system", self.clock(), adjustment_line_id=adj.id)
                confirmed.append(e.id)
                break
        return confirmed

    # ============================================================ cobrança
    def billing_context(self, tenant_id: str) -> TenantBillingContext:
        td = self.store.tenant(tenant_id)
        return TenantBillingContext(tenant_id, td.onboarding.active, td.contract, len(td.reconciled_cycles))

    def emit_floor(self, tenant_id: str, period_id: str, gateway: BillingGateway | None = None):
        td = self.store.tenant(tenant_id)
        if any(c.charge_type is ChargeType.PISO and c.period_id == period_id for c in td.charges.values()):
            raise ValueError("piso já emitido para o período")
        c = self.billing.emit_floor(self.billing_context(tenant_id), period_id, gateway)
        td.charges[c.id] = c
        return c

    def emit_variable(self, tenant_id: str, period_id: str, gateway: BillingGateway, until: datetime | None = None):
        td = self.store.tenant(tenant_id)
        c = self.billing.emit_variable(self.billing_context(tenant_id), td.ledger, period_id, gateway, self.clock(), until)
        if c is not None:
            td.charges[c.id] = c
        return c
