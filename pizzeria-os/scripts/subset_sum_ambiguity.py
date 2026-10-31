"""Simulação: com que frequência o caminho degradado consegue atribuição ÚNICA?

Modelo: n pedidos esperados sem par no ciclo (líquido entre R$ 20 e R$ 120, uniforme, em centavos);
o depósito agregado é a soma de k = n/2 deles (o restante cai no ciclo seguinte). Mede a fração de
depósitos com atribuição única. Hipótese da simulação, não dado de campo.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conciliacao.subset_sum import SolveStatus, solve  # noqa: E402


def run(n: int, trials: int, seed: int = 42) -> float:
    rng = random.Random(seed)
    unique = 0
    for _ in range(trials):
        items = [(f"o{i}", rng.randint(2_000, 12_000)) for i in range(n)]
        picked = rng.sample(items, max(1, n // 2))
        if solve(sum(a for _, a in picked), items).status is SolveStatus.UNIQUE:
            unique += 1
    return unique / trials


if __name__ == "__main__":
    print("pedidos_sem_par  atribuicao_unica")
    for n in (4, 6, 8, 10, 12, 16, 20, 30, 50):
        print(f"{n:>15}  {run(n, 200):>15.0%}")
