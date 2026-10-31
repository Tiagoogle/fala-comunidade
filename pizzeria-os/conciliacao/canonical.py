"""Passe 0 — Canonicalização: normaliza referências, mapeia datas para ciclo, converte para centavos,
deduplica por hash. O formato real do relatório do iFood é parte da Incógnita 3, por isso o parser
de repasse recebe um mapeamento de colunas explícito em vez de assumir um layout.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from .fees import CycleCalendar
from .models import BankTransaction, Channel, EventType, SettlementLine
from .money import parse_brl

_REF_CLEAN = re.compile(r"[^A-Z0-9]")
_CHANNEL_AFFIXES = re.compile(r"^(IFOOD|IF|RAPPI|RP)|(IFOOD|RAPPI)$")
_DIGITS = re.compile(r"\d+")


def normalize_ref(ref: str | None) -> str | None:
    """Canonicaliza external_order_ref (§6.2): maiúsculas, sem hífens/separadores, sem prefixo/sufixo
    de canal e sem zeros à esquerda. '#if-000123-IFOOD' → '123'."""
    if ref is None:
        return None
    r = _REF_CLEAN.sub("", str(ref).strip().upper())
    r = _CHANNEL_AFFIXES.sub("", r).lstrip("0")
    return r or None


def loose_ref(ref: str | None) -> str | None:
    """Chave frouxa para a re-canonicalização do Passe 3 (CT-3.2): apenas dígitos, sem zeros à esquerda."""
    if ref is None:
        return None
    digits = "".join(_DIGITS.findall(str(ref))).lstrip("0")
    return digits or None


def source_hash(*parts) -> str:
    payload = json.dumps([str(p) for p in parts], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def parse_date(value: str) -> date:
    v = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"data em formato não reconhecido: {value!r}")


@dataclass
class SettlementColumnMap:
    order_ref: str | None = "pedido"          # None = relatório agregado (caminho degradado)
    net: str = "valor_liquido"
    line_type: str | None = "tipo"
    settlement_date: str = "data_repasse"
    type_aliases: dict[str, EventType] = field(default_factory=lambda: {
        "venda": EventType.SALE, "pedido": EventType.SALE, "sale": EventType.SALE,
        "promocao": EventType.PROMO, "promoção": EventType.PROMO, "promo": EventType.PROMO,
        "estorno": EventType.REFUND, "cancelamento": EventType.REFUND, "refund": EventType.REFUND,
        "ajuste": EventType.ADJUSTMENT, "adjustment": EventType.ADJUSTMENT,
    })


@dataclass
class ParseReport:
    accepted: int = 0
    duplicates: int = 0
    errors: list[str] = field(default_factory=list)


def parse_settlement_csv(
    tenant_id: str, channel: Channel, text: str, calendar: CycleCalendar,
    columns: SettlementColumnMap | None = None, seen_hashes: set[str] | None = None,
    delimiter: str | None = None,
) -> tuple[list[SettlementLine], ParseReport]:
    cols = columns or SettlementColumnMap()
    seen = seen_hashes if seen_hashes is not None else set()
    report = ParseReport()
    if delimiter is None:
        delimiter = ";" if text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    lines: list[SettlementLine] = []
    for i, row in enumerate(reader, start=2):
        try:
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            ref = normalize_ref(row.get(cols.order_ref)) if cols.order_ref else None
            net = parse_brl(row[cols.net])
            sdate = parse_date(row[cols.settlement_date])
            raw_type = row.get(cols.line_type, "venda").lower() if cols.line_type else "venda"
            ltype = cols.type_aliases.get(raw_type)
            if ltype is None:
                raise ValueError(f"tipo de linha desconhecido: {raw_type!r}")
            h = source_hash(tenant_id, channel.value, ref, net, sdate, ltype.value, i if ref is None else "")
            if h in seen:
                report.duplicates += 1
                continue
            seen.add(h)
            lines.append(SettlementLine(
                tenant_id=tenant_id, channel=channel, external_order_ref=ref,
                settlement_cycle_id=calendar.cycle_id(channel, sdate), reported_net_cents=net,
                line_type=ltype, settlement_date=sdate, source_hash=h, raw_payload=row,
            ))
            report.accepted += 1
        except (KeyError, ValueError) as exc:
            report.errors.append(f"linha {i}: {exc}")
    return lines, report


def parse_bank_csv(
    tenant_id: str, text: str, seen_hashes: set[str] | None = None,
    date_col: str = "data", amount_col: str = "valor", desc_col: str = "descricao",
) -> tuple[list[BankTransaction], ParseReport]:
    seen = seen_hashes if seen_hashes is not None else set()
    report = ParseReport()
    first = text.splitlines()[0] if text.strip() else ""
    delimiter = ";" if first.count(";") > first.count(",") else ","
    out: list[BankTransaction] = []
    for i, row in enumerate(csv.DictReader(io.StringIO(text), delimiter=delimiter), start=2):
        try:
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            d = parse_date(row[date_col])
            amt = parse_brl(row[amount_col])
            desc = row.get(desc_col, "")
            h = source_hash(tenant_id, d, amt, desc)
            if h in seen:
                report.duplicates += 1
                continue
            seen.add(h)
            out.append(BankTransaction(tenant_id, amt, d, desc, h))
            report.accepted += 1
        except (KeyError, ValueError) as exc:
            report.errors.append(f"linha {i}: {exc}")
    return out, report


_OFX_TXN = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.S | re.I)
_OFX_TAG = re.compile(r"<(\w+)>([^<\r\n]*)")


def parse_bank_ofx(tenant_id: str, text: str, seen_hashes: set[str] | None = None) -> tuple[list[BankTransaction], ParseReport]:
    """Parser OFX mínimo (SGML 1.x e XML 2.x). Usa FITID quando disponível como chave de dedup."""
    seen = seen_hashes if seen_hashes is not None else set()
    report = ParseReport()
    out: list[BankTransaction] = []
    for n, block in enumerate(_OFX_TXN.findall(text), start=1):
        tags = {k.upper(): v.strip() for k, v in _OFX_TAG.findall(block)}
        try:
            d = parse_date(tags["DTPOSTED"][:8])
            amt = parse_brl(tags["TRNAMT"])
            desc = tags.get("MEMO") or tags.get("NAME", "")
            h = source_hash(tenant_id, tags.get("FITID") or (d, amt, desc))
            if h in seen:
                report.duplicates += 1
                continue
            seen.add(h)
            out.append(BankTransaction(tenant_id, amt, d, desc, h))
            report.accepted += 1
        except (KeyError, ValueError) as exc:
            report.errors.append(f"transação {n}: {exc}")
    return out, report
