"""Motor de conciliação — cascata de passes (PRD §5).

Cada passe resolve o que consegue de forma determinística e passa adiante só o resíduo.
Caminho primário: relatório itemizado por pedido. O caminho degradado (subset-sum) e o
Passe 4 (bancário) estão travados por decisão (Incógnita 3) e são reportados como bloqueados.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .canonical import source_hash
from .gates import Branch, DecisionGates, Gate
from .models import (
    EventType, ExceptionStatus, ExceptionType, ExpectedReceivable, MatchMethod, MatchStatus,
    ReconciliationException, ReconciliationMatch, SettlementLine,
)
from .money import apply_bps, fmt_brl, tolerance_cents


@dataclass(frozen=True)
class EngineParams:
    tolerance_floor_cents: int = 2
    tolerance_pct_bps: int = 50
    # deriva sistemática: deltas absorvidos pela tolerância, mesmo sinal, por canal+ciclo
    drift_min_matches: int = 10
    drift_same_sign_bps: int = 8000
    drift_min_total_cents: int = 500
    # tolerância para atribuir a divergência de comissão a um percentual efetivo diferente
    commission_attribution_min_bps: int = 25


@dataclass
class ReconciliationResult:
    matches: list[ReconciliationMatch] = field(default_factory=list)
    exceptions: list[ReconciliationException] = field(default_factory=list)
    adjustment_lines: list[SettlementLine] = field(default_factory=list)
    pending_expected: list[ExpectedReceivable] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _fingerprint(*parts) -> str:
    return source_hash("exc", *parts)[:32]


def reconcile(
    tenant_id: str,
    expected: list[ExpectedReceivable],
    settlements: list[SettlementLine],
    closed_cycles: set[str],
    gates: DecisionGates,
    params: EngineParams = EngineParams(),
) -> ReconciliationResult:
    for item in (*expected, *settlements):
        if item.tenant_id != tenant_id:
            raise PermissionError("item de outro tenant entregue ao motor — violação de isolamento")

    res = ReconciliationResult()

    # ---- Passe 0 (complemento): separa ajustes e linhas sem referência -------------------
    itemized: list[SettlementLine] = []
    aggregate: list[SettlementLine] = []
    for s in settlements:
        if s.line_type is EventType.ADJUSTMENT:
            res.adjustment_lines.append(s)  # consumidas pelo loop de confirmação (ledger), não pelo matching
        elif s.external_order_ref is None:
            aggregate.append(s)
        else:
            itemized.append(s)

    if aggregate:
        total = sum(s.reported_net_cents for s in aggregate)
        res.blocked.append(
            f"Caminho degradado: {len(aggregate)} linha(s) sem referência por pedido ({fmt_brl(total)}). "
            f"Atribuição por subset-sum não implementada — Incógnita 3 está "
            f"'{gates.branch(Gate.SETTLEMENT_ITEMIZED).value}'."
        )

    exp_by_ref: dict[str, list[ExpectedReceivable]] = defaultdict(list)
    for e in expected:
        exp_by_ref[e.external_order_ref].append(e)
    set_by_ref: dict[str, list[SettlementLine]] = defaultdict(list)
    for s in itemized:
        set_by_ref[s.external_order_ref].append(s)

    within_tol_by_bucket: dict[tuple[str, str], list[ReconciliationMatch]] = defaultdict(list)
    exp_residual: list[ExpectedReceivable] = []
    set_residual: list[SettlementLine] = []

    # ---- Passe 1 — chave determinística -------------------------------------------------
    for ref in sorted(set(exp_by_ref) | set(set_by_ref)):
        E, S = exp_by_ref.get(ref, []), set_by_ref.get(ref, [])
        if not E or not S:
            exp_residual.extend(E)
            set_residual.extend(S)
            continue

        e_types = defaultdict(list)
        for e in E:
            e_types[e.event_type].append(e)
        s_types = defaultdict(list)
        for s in S:
            s_types[s.line_type].append(s)

        order_gross = sum(e.gross_cents for e in E if e.event_type is EventType.SALE)
        tol = tolerance_cents(order_gross, params.tolerance_floor_cents, params.tolerance_pct_bps)

        # Layout sem linha própria de promoção: a promo vem líquida dentro da linha de venda.
        fold_promo = EventType.PROMO in e_types and EventType.PROMO not in s_types and EventType.SALE in s_types
        groups: list[tuple[list[EventType], MatchMethod]] = []
        if fold_promo:
            groups.append(([EventType.SALE, EventType.PROMO], MatchMethod.KEY_ORDER))
        for t in (EventType.SALE, EventType.PROMO, EventType.REFUND):
            if fold_promo and t in (EventType.SALE, EventType.PROMO):
                continue
            groups.append(([t], MatchMethod.KEY_EVENT))

        for types, method in groups:
            e_grp = [e for t in types for e in e_types.get(t, [])]
            s_grp = [s for s in s_types.get(types[0], [])]
            if not e_grp or not s_grp:
                exp_residual.extend(e_grp)
                set_residual.extend(s_grp)
                continue
            exp_net = sum(e.expected_net_cents for e in e_grp)
            rep_net = sum(s.reported_net_cents for s in s_grp)
            delta = rep_net - exp_net
            if delta == 0:
                status, conf = MatchStatus.MATCHED, 1.0
            elif abs(delta) <= tol:
                status, conf = MatchStatus.WITHIN_TOLERANCE, 0.98
            else:
                status, conf = MatchStatus.DIVERGENT, 1.0
            cycle = e_grp[0].cycle_id
            m = ReconciliationMatch(
                tenant_id=tenant_id, expected_ids=[e.id for e in e_grp], settlement_line_ids=[s.id for s in s_grp],
                match_method=method, confidence=conf if method is MatchMethod.KEY_EVENT else conf * 0.97,
                delta_cents=delta, status=status, order_ref=ref, cycle_id=cycle,
            )
            res.matches.append(m)
            if status is MatchStatus.WITHIN_TOLERANCE:
                within_tol_by_bucket[(e_grp[0].channel.value, cycle)].append(m)
            elif status is MatchStatus.DIVERGENT:
                cause = _probable_cause(types, e_grp, rep_net, delta, tol, params)
                amount = -delta  # positivo = lojista recebeu menos que o contrato
                res.exceptions.append(ReconciliationException(
                    tenant_id=tenant_id, type=ExceptionType.TAXA_DIVERGENTE, amount_cents=amount,
                    order_ref=ref, cycle_id=cycle,
                    probable_cause=cause if amount > 0 else f"{cause} (pagamento a maior — risco de estorno futuro, não recuperável)",
                    status=ExceptionStatus.OPEN if amount > 0 else ExceptionStatus.HUMAN_QUEUE,
                    match_id=m.id, fingerprint=_fingerprint(ExceptionType.TAXA_DIVERGENTE.value, ref, *[t.value for t in types]),
                ))

    # ---- Deriva sistemática: o ponto cego da tolerância ---------------------------------
    for (channel, cycle), ms in within_tol_by_bucket.items():
        if len(ms) < params.drift_min_matches:
            continue
        neg = [m for m in ms if m.delta_cents < 0]
        total = sum(m.delta_cents for m in neg)
        if len(neg) * 10_000 >= params.drift_same_sign_bps * len(ms) and -total >= params.drift_min_total_cents:
            res.exceptions.append(ReconciliationException(
                tenant_id=tenant_id, type=ExceptionType.DERIVA_SISTEMATICA, amount_cents=-total,
                order_ref=None, cycle_id=cycle,
                probable_cause=(f"{len(neg)}/{len(ms)} pedidos absorvidos pela tolerância com delta negativo "
                                f"somando {fmt_brl(total)} — padrão de erro sistemático abaixo do limiar por pedido"),
                fingerprint=_fingerprint(ExceptionType.DERIVA_SISTEMATICA.value, channel, cycle),
            ))

    # ---- Passe 2 — resíduo de pedidos (venda sem repasse) -------------------------------
    for e in exp_residual:
        if e.cycle_id not in closed_cycles or e.expected_net_cents <= 0:
            res.pending_expected.append(e)  # ciclo aberto, ou débito futuro (estorno/promo) ainda não liquidado
            continue
        res.exceptions.append(ReconciliationException(
            tenant_id=tenant_id, type=ExceptionType.VENDA_SEM_REPASSE, amount_cents=e.expected_net_cents,
            order_ref=e.external_order_ref, cycle_id=e.cycle_id,
            probable_cause="pedido esperado sem linha de repasse após fechamento do ciclo",
            fingerprint=_fingerprint(ExceptionType.VENDA_SEM_REPASSE.value, e.external_order_ref, e.event_type.value),
        ))

    # ---- Passe 3 — resíduo de repasses (fila humana) ------------------------------------
    for s in set_residual:
        res.exceptions.append(ReconciliationException(
            tenant_id=tenant_id, type=ExceptionType.REPASSE_SEM_VENDA, amount_cents=s.reported_net_cents,
            order_ref=s.external_order_ref, cycle_id=s.settlement_cycle_id,
            probable_cause="linha de repasse sem pedido correspondente (pedido fora do PDV ou referência divergente)",
            status=ExceptionStatus.HUMAN_QUEUE,
            fingerprint=_fingerprint(ExceptionType.REPASSE_SEM_VENDA.value, s.source_hash),
        ))

    # ---- Passe 4 — bancário -------------------------------------------------------------
    res.blocked.append(
        "Passe 4 (bancário: antecipação / diferença de caixa) não implementado por decisão do PRD §3 — "
        f"depende da Incógnita 3 (atual: '{gates.branch(Gate.SETTLEMENT_ITEMIZED).value}')."
    )

    n_itemized = len(itemized)
    auto = sum(len(m.settlement_line_ids) for m in res.matches if m.status is not MatchStatus.DIVERGENT)
    res.metrics = {
        "expected_events": len(expected),
        "settlement_lines_itemized": n_itemized,
        "settlement_lines_aggregate": len(aggregate),
        "adjustment_lines": len(res.adjustment_lines),
        "auto_match_rate": round(auto / n_itemized, 4) if n_itemized else None,
        "auto_match_target": 0.95 if gates.branch(Gate.SETTLEMENT_ITEMIZED) is not Branch.EXPENSIVE else 0.70,
        "exceptions_by_type": _count(e.type.value for e in res.exceptions),
        "recoverable_cents": sum(e.amount_cents for e in res.exceptions
                                 if e.amount_cents > 0 and e.type is not ExceptionType.REPASSE_SEM_VENDA),
    }
    return res


def _count(it) -> dict:
    out: dict[str, int] = defaultdict(int)
    for k in it:
        out[k] += 1
    return dict(out)


def _probable_cause(types, e_grp, rep_net, delta, tol, params: EngineParams) -> str:
    comps = {}
    for e in e_grp:
        comps.update(e.components)

    if EventType.PROMO in types:
        platform_share = comps.get("platform_share_cents", 0)
        if platform_share and abs(delta + platform_share) <= tol:
            return "promoção cofinanciada debitada integralmente do lojista"

    if types == [EventType.REFUND]:
        reversal = comps.get("commission_reversal_cents", 0)
        if reversal and abs(delta + reversal) <= tol:
            return "estorno sem reversão da comissão prevista em contrato"

    if EventType.SALE in types and "commission_bps" in comps:
        sale = next(e for e in e_grp if e.event_type is EventType.SALE)
        base = sale.gross_cents
        if comps.get("commission_base") == "net_of_promo":
            base -= comps.get("promo_discount_cents", 0)
        if base > 0:
            implied_bps = comps["commission_bps"] - (delta * 10_000) // base
            if abs(implied_bps - comps["commission_bps"]) >= params.commission_attribution_min_bps:
                return (f"comissão efetiva implícita ~{implied_bps / 100:.2f}% vs {comps['commission_bps'] / 100:.2f}% "
                        f"contratado (ou taxa fixa divergente)")
    return f"divergência não classificada de {fmt_brl(delta)}"
