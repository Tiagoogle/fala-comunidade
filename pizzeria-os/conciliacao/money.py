"""Aritmética monetária em centavos inteiros. Nunca ponto flutuante.

Percentuais são expressos em basis points (bps): 23% = 2300 bps.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

BPS = 10_000


def apply_bps(amount_cents: int, bps: int) -> int:
    """amount * bps / 10000 com arredondamento half-up simétrico (half away from zero)."""
    if not isinstance(amount_cents, int) or not isinstance(bps, int):
        raise TypeError("apply_bps exige inteiros (centavos e bps)")
    product = abs(amount_cents) * bps
    q, r = divmod(product, BPS)
    if r * 2 >= BPS:
        q += 1
    return q if amount_cents >= 0 else -q


def tolerance_cents(gross_cents: int, floor_cents: int = 2, pct_bps: int = 50) -> int:
    """Tolerância do Passe 0: max(R$ 0,02, 0,5% do bruto da linha) — parâmetros por hipótese (PRD §5)."""
    return max(floor_cents, apply_bps(abs(gross_cents), pct_bps))


def parse_brl(value: str) -> int:
    """Converte texto monetário em centavos. Aceita '1.234,56', '1234.56', 'R$ -12,30', '(12,30)'."""
    if value is None:
        raise ValueError("valor monetário ausente")
    s = str(value).strip().replace("R$", "").replace(" ", "").replace(" ", "")
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    if s.startswith("-"):
        negative, s = True, s[1:]
    if not s:
        raise ValueError(f"valor monetário vazio: {value!r}")
    if "," in s and "." in s:
        # o separador que aparece por último é o decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation as exc:
        raise ValueError(f"valor monetário inválido: {value!r}") from exc
    cents = d * 100
    if cents != cents.to_integral_value():
        raise ValueError(f"valor com mais de 2 casas decimais: {value!r}")
    result = int(cents)
    return -result if negative else result


def fmt_brl(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    reais, c = divmod(abs(cents), 100)
    inteiro = f"{reais:,}".replace(",", ".")
    return f"{sign}R$ {inteiro},{c:02d}"
