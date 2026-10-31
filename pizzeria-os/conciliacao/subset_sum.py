"""SubsetSumSolver — caminho degradado (Incógnita 3, ramo que encarece).

Pergunta: que subconjunto de pedidos esperados soma o líquido depositado de forma agregada?

Algoritmo: programação dinâmica pseudo-polinomial com bitset em inteiro arbitrário
(bit s ligado = soma s alcançável). Custo O(n · alvo/64) palavras de máquina; viável para
centenas de pedidos e alvos de dezenas de milhares de reais. Acima do orçamento, devolve
TOO_LARGE em vez de travar o worker.

Diferente de uma heurística gulosa, o solver PROVA unicidade: uma atribuição só é aceita
automaticamente se nenhum outro subconjunto cai na janela de tolerância. Atribuição ambígua
vai para a fila humana — atribuir o pedido errado a um repasse é pior do que não atribuir.

Limitação estrutural (não é bug): o solver casa contra o líquido ESPERADO. Se a plataforma
cobrou tarifa divergente em qualquer pedido do lote, a soma esperada não bate com o depósito e
o resultado é NONE — exatamente quando há algo a recuperar. O degradado detecta "o lote não
fecha", nunca "qual pedido divergiu".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SolveStatus(str, Enum):
    UNIQUE = "unique"
    AMBIGUOUS = "ambiguous"
    NONE = "none"
    TOO_LARGE = "too_large"


@dataclass(frozen=True)
class SolveResult:
    status: SolveStatus
    keys: tuple[str, ...] = ()
    total_cents: int = 0
    reason: str = ""


@dataclass(frozen=True)
class SolverLimits:
    max_items: int = 2_000
    max_bitset_cells: int = 400_000_000   # n · (alvo + tol) — orçamento de memória (~50 MB)


def _reach_table(amounts: list[int], width: int) -> list[int]:
    """reach[i] = bitset das somas alcançáveis com os i primeiros itens."""
    mask = (1 << (width + 1)) - 1
    reach = [1]
    cur = 1
    for a in amounts:
        cur = (cur | (cur << a)) & mask
        reach.append(cur)
    return reach


def _reach_final(amounts: list[int], width: int, skip: int | None = None) -> int:
    mask = (1 << (width + 1)) - 1
    cur = 1
    for i, a in enumerate(amounts):
        if i != skip:
            cur = (cur | (cur << a)) & mask
    return cur


def _window_hits(bits: int, lo: int, hi: int) -> int:
    return (bits >> lo) & ((1 << (hi - lo + 1)) - 1)


def solve(target_cents: int, items: list[tuple[str, int]], tolerance_cents: int = 0,
          limits: SolverLimits = SolverLimits()) -> SolveResult:
    if type(target_cents) is not int or any(type(a) is not int for _, a in items):
        raise TypeError("subset-sum opera apenas sobre inteiros em centavos")
    if target_cents <= 0:
        return SolveResult(SolveStatus.NONE, reason="alvo não positivo")
    usable = [(k, a) for k, a in items if 0 < a <= target_cents + tolerance_cents]
    if len(usable) > limits.max_items:
        return SolveResult(SolveStatus.TOO_LARGE, reason=f"{len(usable)} itens > limite {limits.max_items}")
    lo, hi = max(1, target_cents - tolerance_cents), target_cents + tolerance_cents
    if len(usable) * (hi + 1) > limits.max_bitset_cells:
        return SolveResult(SolveStatus.TOO_LARGE, reason="orçamento de memória do bitset excedido")

    keys = [k for k, _ in usable]
    amounts = [a for _, a in usable]
    reach = _reach_table(amounts, hi)
    hits = _window_hits(reach[-1], lo, hi)
    if not hits:
        return SolveResult(SolveStatus.NONE, reason="nenhum subconjunto de pedidos esperados soma o valor depositado")

    # soma alcançável mais próxima do alvo (empate → a menor)
    best = min((s for s in range(lo, hi + 1) if (hits >> (s - lo)) & 1), key=lambda s: (abs(s - target_cents), s))

    chosen, s = [], best
    for i in range(len(amounts) - 1, -1, -1):
        if (reach[i] >> s) & 1:
            continue  # alcançável sem o item i
        chosen.append(i)
        s -= amounts[i]
    assert s == 0
    chosen_set = set(chosen)

    # Prova de unicidade. Qualquer outra solução T ≠ S na janela: (a) omite algum item de S, ou
    # (b) é superconjunto estrito de S — e então contém um item extra ≤ hi - soma(S).
    slack = hi - best
    if any(amounts[j] <= slack for j in range(len(amounts)) if j not in chosen_set):
        return SolveResult(SolveStatus.AMBIGUOUS, reason="há item adicional que mantém a soma na tolerância")
    for j in chosen:
        if _window_hits(_reach_final(amounts, hi, skip=j), lo, hi):
            return SolveResult(SolveStatus.AMBIGUOUS, reason="mais de um subconjunto de pedidos fecha o depósito")

    return SolveResult(SolveStatus.UNIQUE, tuple(sorted(keys[i] for i in chosen)), best)
