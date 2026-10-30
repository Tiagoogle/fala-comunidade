"""Parâmetros de decisão bloqueadores (PRD §3).

Cada incógnita tem dois ramos que produzem desenhos de engenharia distintos. Enquanto
estiver UNRESOLVED, o código que depende dela recusa-se a executar — construir para o
ramo errado é retrabalho estrutural. A resolução é uma decisão registrada (evidência +
data), não um toggle silencioso.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Branch(str, Enum):
    UNRESOLVED = "unresolved"
    SIMPLIFIES = "simplifies"
    EXPENSIVE = "expensive"


class Gate(str, Enum):
    IFOOD_TRACEABLE_ADJUSTMENT = "ifood_traceable_adjustment"   # Incógnita 1
    GATEWAY_VARIABLE_AMOUNT = "gateway_variable_amount"         # Incógnita 2
    SETTLEMENT_ITEMIZED = "settlement_itemized"                 # Incógnita 3


GATE_DESCRIPTIONS = {
    Gate.IFOOD_TRACEABLE_ADJUSTMENT: (
        "Incógnita 1 — o relatório financeiro do iFood expõe linha de ajuste vinculável ao "
        "external_order_ref no ciclo de liquidação? Trava confirmation_method auto vs manual."
    ),
    Gate.GATEWAY_VARIABLE_AMOUNT: (
        "Incógnita 2 — o preapproval do Mercado Pago cobra valor variável por ciclo? "
        "Trava a arquitetura de billing_charge (mandato único vs dois instrumentos). "
        "Exige verificação em sandbox contra a documentação vigente."
    ),
    Gate.SETTLEMENT_ITEMIZED: (
        "Incógnita 3 — o relatório de repasse é itemizado por pedido? Trava o caminho "
        "default do motor, o Passe 4 e a taxa-alvo de auto-match."
    ),
}


class DecisionGateBlocked(RuntimeError):
    def __init__(self, gate: Gate, needed: str):
        self.gate = gate
        super().__init__(f"Bloqueado por decisão pendente [{gate.value}]: {needed}. {GATE_DESCRIPTIONS[gate]}")


@dataclass
class GateResolution:
    branch: Branch = Branch.UNRESOLVED
    evidence: str | None = None
    resolved_on: date | None = None


@dataclass
class DecisionGates:
    resolutions: dict[Gate, GateResolution] = field(
        default_factory=lambda: {g: GateResolution() for g in Gate}
    )

    def branch(self, gate: Gate) -> Branch:
        return self.resolutions[gate].branch

    def resolve(self, gate: Gate, branch: Branch, evidence: str, resolved_on: date) -> None:
        if branch is Branch.UNRESOLVED:
            raise ValueError("use resolve() apenas para um ramo concreto")
        if not evidence or len(evidence.strip()) < 10:
            raise ValueError("resolução exige evidência de fonte primária (ex.: link da doc, ID do teste em sandbox)")
        self.resolutions[gate] = GateResolution(branch, evidence.strip(), resolved_on)

    def require(self, gate: Gate, needed: str, branch: Branch | None = None) -> Branch:
        """Exige que o gate esteja resolvido (e, opcionalmente, num ramo específico)."""
        current = self.branch(gate)
        if current is Branch.UNRESOLVED or (branch is not None and current is not branch):
            raise DecisionGateBlocked(gate, needed)
        return current

    def snapshot(self) -> dict:
        return {
            g.value: {
                "branch": r.branch.value,
                "evidence": r.evidence,
                "resolved_on": r.resolved_on.isoformat() if r.resolved_on else None,
                "description": GATE_DESCRIPTIONS[g],
            }
            for g, r in self.resolutions.items()
        }
