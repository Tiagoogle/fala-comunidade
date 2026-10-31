"""ReconciliationEngine — cascata de passes (Prompt Mestre §6).

    run_pass0  canonicalização: separa ajustes, linhas itemizadas, linhas agregadas; dedup
    run_pass1  chave determinística (external_order_ref) → matches + taxa_divergente
    run_pass2  resíduo de pedidos → venda_sem_repasse (só após o ciclo fechar)
    run_pass3  resíduo de repasses → re-canonicalização frouxa, depois repasse_sem_venda (fila humana)
    run_pass4  bancário: soma do ciclo de repasse contra o depósito → antecipacao / diferenca_caixa

Caminho primário vs degradado (INVARIANTE 7): linhas COM referência sempre vão pelo caminho
primário, qualquer que seja a flag. A flag settlement_itemized decide apenas o destino das linhas
SEM referência: false → SubsetSumSolver (fila assíncrona); true → anomalia de layout para revisão.
Assim o default false (§8.4) não rebaixa um tenant itemizado para o caminho caro.

O motor é puro sobre suas entradas e idempotente: reexecutar com os mesmos dados produz as mesmas
exceções (mesmo fingerprint).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from .canonical import loose_ref, source_hash
from .fees import CycleCalendar
from .models import (
    BankTransaction, Channel, EventType, ExceptionStatus, ExceptionType, ExpectedReceivable, MatchMethod,
    MatchStatus, RECOVERABLE_TYPES, ReconciliationException, ReconciliationMatch, SettlementLine,
)
from .money import fmt_brl, tolerance_cents
from .subset_sum import SolveResult, SolveStatus


@dataclass(frozen=True)
class EngineParams:
    tolerance_floor_cents: int = 2
    tolerance_pct_bps: int = 50
    drift_min_matches: int = 10
    drift_same_sign_bps: int = 8000
    drift_min_total_cents: int = 500
    commission_attribution_min_bps: int = 25
    bank_tolerance_cents: int = 2
    bank_lag_days: int = 3
    deposit_keywords: tuple[tuple[Channel, str], ...] = ((Channel.IFOOD, "IFOOD"), (Channel.RAPPI, "RAPPI"))
    subset_sum_tolerance_cents: int = 2


@dataclass
class Pass0Output:
    expected: list[ExpectedReceivable]
    itemized: list[SettlementLine]
    aggregate: list[SettlementLine]
    adjustments: list[SettlementLine]
    bank: list[BankTransaction]


@dataclass
class EngineInput:
    tenant_id: str
    expected: list[ExpectedReceivable]
    settlements: list[SettlementLine]
    bank: list[BankTransaction]
    closed_cycles: set[str]
    settlement_itemized: bool
    # resultado do SubsetSumSolver por id da linha agregada; ausente = ainda não resolvido
    subset_results: dict[str, SolveResult] = field(default_factory=dict)
    subset_pending: set[str] = field(default_factory=set)


@dataclass
class RunResult:
    matches: list[ReconciliationMatch] = field(default_factory=list)
    exceptions: list[ReconciliationException] = field(default_factory=list)
    adjustment_lines: list[SettlementLine] = field(default_factory=list)
    pending_expected: list[ExpectedReceivable] = field(default_factory=list)
    subset_sum_requests: list[SettlementLine] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _fp(*parts) -> str:
    return source_hash("exc", *parts)[:32]


class ReconciliationEngine:
    def __init__(self, calendar: CycleCalendar, params: EngineParams = EngineParams()) -> None:
        self.calendar = calendar
        self.params = params

    # ------------------------------------------------------------------ orquestração
    def run(self, inp: EngineInput, cycle_id: str | None = None) -> RunResult:
        """Aplica os passes em sequência. cycle_id restringe a SAÍDA ao ciclo (de venda para N1/N2,
        de repasse para o Passe 4); o casamento sempre enxerga todos os dados do tenant, porque estorno
        e repasse caem em ciclos posteriores ao da venda."""
        for item in (*inp.expected, *inp.settlements, *inp.bank):
            if item.tenant_id != inp.tenant_id:
                raise PermissionError("item de outro tenant entregue ao motor — violação de isolamento")
        res = RunResult()
        p0 = self.run_pass0(inp, res)
        exp_res, set_res, within = self.run_pass1(inp.tenant_id, p0, res)
        exp_res = self._apply_subset_sum(inp, p0, exp_res, res)
        exp_res, set_res = self._loose_rematch(inp.tenant_id, exp_res, set_res, res, within)
        self._drift(inp.tenant_id, within, res)
        self.run_pass2(inp, exp_res, res)
        self.run_pass3(inp.tenant_id, set_res, res)
        self.run_pass4(inp, p0, res)
        if cycle_id is not None:
            res.matches = [m for m in res.matches if m.cycle_id == cycle_id]
            res.exceptions = [e for e in res.exceptions if e.cycle_id == cycle_id]
        self._metrics(inp, p0, res)
        return res

    # ------------------------------------------------------------------ Passe 0
    def run_pass0(self, inp: EngineInput, res: RunResult) -> Pass0Output:
        seen_exp, expected = set(), []
        for e in inp.expected:
            if e.id not in seen_exp:
                seen_exp.add(e.id)
                expected.append(e)
        seen_set, itemized, aggregate = set(), [], []
        for s in inp.settlements:
            if s.source_hash in seen_set:
                continue
            seen_set.add(s.source_hash)
            if s.line_type is EventType.ADJUSTMENT:
                res.adjustment_lines.append(s)   # loop de confirmação (ledger), não matching
            elif s.external_order_ref is None:
                aggregate.append(s)
            else:
                itemized.append(s)
        seen_bank, bank = set(), []
        for b in inp.bank:
            if b.source_hash not in seen_bank:
                seen_bank.add(b.source_hash)
                bank.append(b)
        return Pass0Output(expected, itemized, aggregate, res.adjustment_lines, bank)

    def tolerance_for(self, gross_cents: int) -> int:
        return tolerance_cents(gross_cents, self.params.tolerance_floor_cents, self.params.tolerance_pct_bps)

    # ------------------------------------------------------------------ Passe 1
    def run_pass1(self, tenant_id: str, p0: Pass0Output, res: RunResult):
        exp_by_ref: dict[str, list[ExpectedReceivable]] = defaultdict(list)
        for e in p0.expected:
            exp_by_ref[e.external_order_ref].append(e)
        set_by_ref: dict[str, list[SettlementLine]] = defaultdict(list)
        for s in p0.itemized:
            set_by_ref[s.external_order_ref].append(s)

        within: dict[tuple[str, str], list[ReconciliationMatch]] = defaultdict(list)
        exp_res: list[ExpectedReceivable] = []
        set_res: list[SettlementLine] = []
        for ref in sorted(set(exp_by_ref) | set(set_by_ref)):
            E, S = exp_by_ref.get(ref, []), set_by_ref.get(ref, [])
            if not E or not S:
                exp_res.extend(E)
                set_res.extend(S)
                continue
            e_left, s_left = self._match_order(tenant_id, ref, E, S, res, within, loose=False)
            exp_res.extend(e_left)
            set_res.extend(s_left)
        return exp_res, set_res, within

    def _match_order(self, tenant_id, ref, E, S, res, within, loose: bool):
        e_types, s_types = defaultdict(list), defaultdict(list)
        for e in E:
            e_types[e.event_type].append(e)
        for s in S:
            s_types[s.line_type].append(s)
        tol = self.tolerance_for(sum(e.gross_cents for e in E if e.event_type is EventType.SALE))

        fold_promo = EventType.PROMO in e_types and EventType.PROMO not in s_types and EventType.SALE in s_types
        groups: list[tuple[list[EventType], MatchMethod]] = []
        if fold_promo:
            groups.append(([EventType.SALE, EventType.PROMO], MatchMethod.KEY_ORDER))
        for t in (EventType.SALE, EventType.PROMO, EventType.REFUND):
            if not (fold_promo and t in (EventType.SALE, EventType.PROMO)):
                groups.append(([t], MatchMethod.KEY_EVENT))

        e_left, s_left = [], []
        for types, method in groups:
            e_grp = [e for t in types for e in e_types.get(t, [])]
            s_grp = list(s_types.get(types[0], []))
            if not e_grp or not s_grp:
                e_left.extend(e_grp)
                s_left.extend(s_grp)
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
            if method is MatchMethod.KEY_ORDER:
                conf = round(conf * 0.97, 4)
            if loose:
                method, conf = MatchMethod.KEY_LOOSE, round(conf * 0.9, 4)
            cycle = e_grp[0].cycle_id
            m = ReconciliationMatch(tenant_id, [e.id for e in e_grp], [s.id for s in s_grp], method, conf,
                                    delta, status, ref, cycle)
            res.matches.append(m)
            if status is MatchStatus.WITHIN_TOLERANCE:
                within[(e_grp[0].channel.value, cycle)].append(m)
            elif status is MatchStatus.DIVERGENT:
                cause = self._probable_cause(types, e_grp, delta, tol)
                amount = -delta
                if loose:
                    cause += f" [casado por re-canonicalização: {s_grp[0].external_order_ref} ≈ {ref}]"
                res.exceptions.append(ReconciliationException(
                    tenant_id, ExceptionType.TAXA_DIVERGENTE, amount, ref, cycle,
                    cause if amount > 0 else f"{cause} (pagamento a maior — risco de estorno futuro, não recuperável)",
                    ExceptionStatus.OPEN if amount > 0 else ExceptionStatus.HUMAN_QUEUE, m.id,
                    _fp(ExceptionType.TAXA_DIVERGENTE.value, ref, *[t.value for t in types]),
                ))
        return e_left, s_left

    def _probable_cause(self, types, e_grp, delta, tol) -> str:
        comps: dict = {}
        for e in e_grp:
            comps.update(e.components)
        if EventType.PROMO in types:
            share = comps.get("platform_share_cents", 0)
            if share and abs(delta + share) <= tol:
                return "promoção cofinanciada debitada integralmente"
        if types == [EventType.REFUND]:
            rev = comps.get("commission_reversal_cents", 0)
            if rev and abs(delta + rev) <= tol:
                return "estorno sem reversão da comissão prevista em contrato"
        if EventType.SALE in types and "commission_bps" in comps:
            sale = next(e for e in e_grp if e.event_type is EventType.SALE)
            base = sale.gross_cents - (comps.get("promo_discount_cents", 0) if comps.get("commission_base") == "net_of_promo" else 0)
            if base > 0:
                implied = comps["commission_bps"] - (delta * 10_000) // base
                if abs(implied - comps["commission_bps"]) >= self.params.commission_attribution_min_bps:
                    return (f"comissão efetiva implícita ~{implied / 100:.2f}% vs {comps['commission_bps'] / 100:.2f}% "
                            f"contratado (ou taxa fixa divergente)")
        return f"divergência não classificada de {fmt_brl(delta)}"

    # ------------------------------------------------------------------ caminho degradado
    def _apply_subset_sum(self, inp: EngineInput, p0: Pass0Output, exp_res, res: RunResult):
        if not p0.aggregate:
            return exp_res
        if inp.settlement_itemized:
            total = sum(s.reported_net_cents for s in p0.aggregate)
            res.warnings.append(
                f"{len(p0.aggregate)} linha(s) agregada(s) ({fmt_brl(total)}) recebida(s) com settlement_itemized=true: "
                "layout do relatório mudou? Linhas enviadas à fila humana, solver NÃO acionado."
            )
            for s in p0.aggregate:
                res.exceptions.append(self._human_aggregate(inp.tenant_id, s, "linha agregada inesperada para tenant itemizado"))
            return exp_res

        attributed: set[str] = set()
        for s in sorted(p0.aggregate, key=lambda x: (x.settlement_date, x.id)):
            r = inp.subset_results.get(s.id)
            if r is None:
                res.subset_sum_requests.append(s)
                continue
            if r.status is SolveStatus.UNIQUE:
                refs = set(r.keys)
                grp = [e for e in exp_res if e.external_order_ref in refs]
                exp_net = sum(e.expected_net_cents for e in grp)
                cycle = grp[0].cycle_id if grp else s.settlement_cycle_id
                res.matches.append(ReconciliationMatch(
                    inp.tenant_id, [e.id for e in grp], [s.id], MatchMethod.SUBSET_SUM, 0.9,
                    s.reported_net_cents - exp_net, MatchStatus.MATCHED if s.reported_net_cents == exp_net
                    else MatchStatus.WITHIN_TOLERANCE, ",".join(sorted(refs)), cycle))
                attributed |= refs
            else:
                res.exceptions.append(self._human_aggregate(inp.tenant_id, s, f"subset-sum {r.status.value}: {r.reason}"))
        return [e for e in exp_res if e.external_order_ref not in attributed]

    def subset_sum_candidates(self, inp: EngineInput, line: SettlementLine) -> list[tuple[str, int]]:
        """Pedidos esperados sem par, mesmo canal, ocorridos até a data do repasse, líquido positivo."""
        res = RunResult()
        p0 = self.run_pass0(inp, res)
        exp_res, _, _ = self.run_pass1(inp.tenant_id, p0, res)
        already = {ref for r in inp.subset_results.values() if r.status is SolveStatus.UNIQUE for ref in r.keys}
        by_ref: dict[str, int] = defaultdict(int)
        for e in exp_res:
            start = date.fromisoformat(e.cycle_id.split(":", 1)[1])
            if e.channel is line.channel and start <= line.settlement_date and e.external_order_ref not in already:
                by_ref[e.external_order_ref] += e.expected_net_cents
        return sorted((k, v) for k, v in by_ref.items() if v > 0)

    @staticmethod
    def _human_aggregate(tenant_id, s: SettlementLine, why: str) -> ReconciliationException:
        return ReconciliationException(
            tenant_id, ExceptionType.REPASSE_SEM_VENDA, s.reported_net_cents, None, s.settlement_cycle_id,
            f"repasse agregado sem atribuição por pedido ({why})", ExceptionStatus.HUMAN_QUEUE,
            fingerprint=_fp(ExceptionType.REPASSE_SEM_VENDA.value, s.source_hash))

    # ------------------------------------------------------------------ Passe 3 (re-canonicalização)
    def _loose_rematch(self, tenant_id, exp_res, set_res, res, within):
        exp_by_loose: dict[str, set[str]] = defaultdict(set)
        for e in exp_res:
            k = loose_ref(e.external_order_ref)
            if k:
                exp_by_loose[k].add(e.external_order_ref)
        set_by_loose: dict[str, list[SettlementLine]] = defaultdict(list)
        for s in set_res:
            k = loose_ref(s.external_order_ref)
            if k:
                set_by_loose[k].append(s)
        used_e, used_s = set(), set()
        for k, lines in set_by_loose.items():
            refs = exp_by_loose.get(k, set())
            if len(refs) != 1:
                continue  # nenhum ou mais de um candidato: não adivinha
            ref = next(iter(refs))
            E = [e for e in exp_res if e.external_order_ref == ref]
            e_left, s_left = self._match_order(tenant_id, ref, E, lines, res, within, loose=True)
            used_e |= {e.id for e in E} - {e.id for e in e_left}
            used_s |= {s.id for s in lines} - {s.id for s in s_left}
        return ([e for e in exp_res if e.id not in used_e], [s for s in set_res if s.id not in used_s])

    # ------------------------------------------------------------------ deriva sistemática
    def _drift(self, tenant_id, within, res: RunResult) -> None:
        p = self.params
        for (channel, cycle), ms in within.items():
            if len(ms) < p.drift_min_matches:
                continue
            neg = [m for m in ms if m.delta_cents < 0]
            total = sum(m.delta_cents for m in neg)
            if len(neg) * 10_000 >= p.drift_same_sign_bps * len(ms) and -total >= p.drift_min_total_cents:
                res.exceptions.append(ReconciliationException(
                    tenant_id, ExceptionType.DERIVA_SISTEMATICA, -total, None, cycle,
                    f"{len(neg)}/{len(ms)} pedidos absorvidos pela tolerância com delta negativo somando {fmt_brl(total)}"
                    " — erro sistemático abaixo do limiar por pedido",
                    fingerprint=_fp(ExceptionType.DERIVA_SISTEMATICA.value, channel, cycle)))

    # ------------------------------------------------------------------ Passe 2
    def run_pass2(self, inp: EngineInput, exp_res, res: RunResult) -> None:
        degraded_open = bool(res.subset_sum_requests or inp.subset_pending)
        for e in exp_res:
            if e.cycle_id not in inp.closed_cycles or e.expected_net_cents <= 0 or degraded_open:
                # ciclo aberto; débito futuro (estorno/promo); ou atribuição por subset-sum ainda pendente
                res.pending_expected.append(e)
                continue
            res.exceptions.append(ReconciliationException(
                inp.tenant_id, ExceptionType.VENDA_SEM_REPASSE, e.expected_net_cents, e.external_order_ref, e.cycle_id,
                "pedido esperado sem linha de repasse após fechamento do ciclo",
                fingerprint=_fp(ExceptionType.VENDA_SEM_REPASSE.value, e.external_order_ref, e.event_type.value)))

    # ------------------------------------------------------------------ Passe 3
    def run_pass3(self, tenant_id: str, set_res, res: RunResult) -> None:
        for s in set_res:
            res.exceptions.append(ReconciliationException(
                tenant_id, ExceptionType.REPASSE_SEM_VENDA, s.reported_net_cents, s.external_order_ref,
                s.settlement_cycle_id,
                "linha de repasse sem pedido correspondente mesmo após re-canonicalização "
                "(pedido fora do PDV ou referência irreconhecível)",
                ExceptionStatus.HUMAN_QUEUE, fingerprint=_fp(ExceptionType.REPASSE_SEM_VENDA.value, s.source_hash)))

    # ------------------------------------------------------------------ Passe 4
    def run_pass4(self, inp: EngineInput, p0: Pass0Output, res: RunResult) -> None:
        """Compara N2 (soma reportada do ciclo de repasse) com N3 (depósito). Não duplica o Passe 1:
        o Passe 1 mede N1 vs N2, o Passe 4 mede N2 vs N3 — divergências disjuntas."""
        if res.subset_sum_requests or inp.subset_pending:
            res.warnings.append("Passe 4 adiado: há atribuições por subset-sum pendentes na fila")
            return
        p = self.params
        lines_by_cycle: dict[tuple[Channel, str], list[SettlementLine]] = defaultdict(list)
        for s in (*p0.itemized, *p0.aggregate, *p0.adjustments):
            lines_by_cycle[(s.channel, s.settlement_cycle_id)].append(s)
        keywords = dict(p.deposit_keywords)
        used: set[str] = set()
        match_by_line = {sid: m for m in res.matches for sid in m.settlement_line_ids}

        for (channel, cycle), lines in sorted(lines_by_cycle.items(), key=lambda kv: kv[0][1]):
            if cycle not in inp.closed_cycles:
                continue
            start = date.fromisoformat(cycle.split(":", 1)[1])
            end = start + timedelta(days=self.calendar.length_days + p.bank_lag_days)
            kw = keywords.get(channel, channel.value.upper())
            deposits = [b for b in p0.bank if b.id not in used and b.amount_cents > 0 and start <= b.value_date < end
                        and kw in b.description.upper()]
            reported = sum(s.reported_net_cents for s in lines)
            deposited = sum(b.amount_cents for b in deposits)
            used |= {b.id for b in deposits}
            diff = deposited - reported
            bank_ref = deposits[0].id if deposits else None
            for s in lines:
                m = match_by_line.get(s.id)
                if m is not None and bank_ref:
                    m.bank_txn_id = bank_ref
            res.matches.append(ReconciliationMatch(
                inp.tenant_id, [], [s.id for s in lines], MatchMethod.BANK, 1.0 if deposits else 0.0, diff,
                MatchStatus.MATCHED if abs(diff) <= p.bank_tolerance_cents else MatchStatus.DIVERGENT,
                f"{channel.value}-deposit", cycle, bank_ref))
            if abs(diff) <= p.bank_tolerance_cents:
                continue
            if diff > 0:
                res.exceptions.append(ReconciliationException(
                    inp.tenant_id, ExceptionType.ANTECIPACAO, diff, None, cycle,
                    f"depósito {fmt_brl(deposited)} maior que repasse reportado {fmt_brl(reported)}: provável antecipação "
                    "de recebíveis — verificar taxa de antecipação nos ciclos seguintes",
                    ExceptionStatus.HUMAN_QUEUE, fingerprint=_fp(ExceptionType.ANTECIPACAO.value, channel.value, cycle)))
            else:
                cause = ("nenhum depósito identificado na janela do ciclo" if not deposits else
                         f"depósito {fmt_brl(deposited)} menor que repasse reportado {fmt_brl(reported)}: "
                         "taxa não prevista, estorno pós-repasse ou divergência no próprio relatório")
                res.exceptions.append(ReconciliationException(
                    inp.tenant_id, ExceptionType.DIFERENCA_CAIXA, -diff, None, cycle, cause,
                    fingerprint=_fp(ExceptionType.DIFERENCA_CAIXA.value, channel.value, cycle)))

    # ------------------------------------------------------------------ métricas
    def _metrics(self, inp: EngineInput, p0: Pass0Output, res: RunResult) -> None:
        order_matches = [m for m in res.matches if m.match_method is not MatchMethod.BANK]
        n_lines = len(p0.itemized) + len(p0.aggregate)
        auto = sum(len(m.settlement_line_ids) for m in order_matches if m.status is not MatchStatus.DIVERGENT)
        res.metrics = {
            "expected_events": len(p0.expected),
            "settlement_lines_itemized": len(p0.itemized),
            "settlement_lines_aggregate": len(p0.aggregate),
            "adjustment_lines": len(p0.adjustments),
            "auto_match_rate": round(auto / n_lines, 4) if n_lines else None,
            "auto_match_target": 0.95 if not p0.aggregate else 0.70,
            "exceptions_by_type": dict(_count(e.type.value for e in res.exceptions)),
            "recoverable_cents": sum(e.amount_cents for e in res.exceptions
                                     if e.amount_cents > 0 and e.type in RECOVERABLE_TYPES),
            "subset_sum_requested": len(res.subset_sum_requests),
        }


def _count(it):
    out: dict[str, int] = defaultdict(int)
    for k in it:
        out[k] += 1
    return out
