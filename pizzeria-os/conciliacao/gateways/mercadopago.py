"""Adaptadores de cobrança Mercado Pago — os dois ramos da Incógnita 2.

ATENÇÃO — NÃO VERIFICADO EM SANDBOX. Endpoints e payloads seguem a API pública do Mercado Pago
conforme conhecida até jan/2026 (POST/PUT /preapproval, POST /v1/payments). A Fase 0 do roadmap
exige confirmar contra a documentação vigente antes de qualquer cobrança real.

INVARIANTE 1 na fronteira: a API recebe número decimal em reais. A conversão centavos → literal
decimal é feita por formatação de inteiros (sem float) e o JSON é serializado com o número cru.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Protocol

API = "https://api.mercadopago.com"


def cents_to_amount_literal(cents: int) -> str:
    if type(cents) is not int or cents < 0:
        raise TypeError("valor deve ser int não negativo em centavos")
    return f"{cents // 100}.{cents % 100:02d}"


class _Raw(str):
    """Marca um literal numérico já formatado para ser emitido sem aspas."""


_RAW_RE = re.compile(r'"__RAW__([0-9.]+)__"')


def encode_json(payload: dict) -> str:
    def conv(o):
        if isinstance(o, _Raw):
            return f"__RAW__{o}__"
        if isinstance(o, dict):
            return {k: conv(v) for k, v in o.items()}
        if isinstance(o, list):
            return [conv(v) for v in o]
        if isinstance(o, float):
            raise TypeError("float proibido no payload do gateway (INVARIANTE 1)")
        return o
    return _RAW_RE.sub(r"\1", json.dumps(conv(payload), ensure_ascii=False))


class HttpTransport(Protocol):
    def request(self, method: str, url: str, headers: dict, body: str | None) -> dict: ...


@dataclass
class MercadoPagoClient:
    access_token: str
    transport: HttpTransport

    def _call(self, method: str, path: str, payload: dict | None, idempotency_key: str | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        return self.transport.request(method, API + path, headers, encode_json(payload) if payload is not None else None)

    def create_preapproval(self, payer_email: str, amount_cents: int, reason: str, external_reference: str) -> dict:
        return self._call("POST", "/preapproval", {
            "reason": reason, "external_reference": external_reference, "payer_email": payer_email,
            "auto_recurring": {"frequency": 1, "frequency_type": "months",
                               "transaction_amount": _Raw(cents_to_amount_literal(amount_cents)), "currency_id": "BRL"},
            "status": "pending",
        })

    def update_preapproval_amount(self, preapproval_id: str, amount_cents: int) -> dict:
        return self._call("PUT", f"/preapproval/{preapproval_id}", {
            "auto_recurring": {"transaction_amount": _Raw(cents_to_amount_literal(amount_cents)), "currency_id": "BRL"},
        })

    def create_payment(self, customer_id: str, card_token: str, amount_cents: int, description: str,
                       idempotency_key: str) -> dict:
        return self._call("POST", "/v1/payments", {
            "transaction_amount": _Raw(cents_to_amount_literal(amount_cents)), "description": description,
            "token": card_token, "installments": 1, "payer": {"type": "customer", "id": customer_id},
        }, idempotency_key=idempotency_key)


@dataclass
class TenantBillingAccount:
    payer_email: str
    preapproval_id: str | None = None
    customer_id: str | None = None
    card_token: str | None = None


class BillingGateway(Protocol):
    instrument_floor: str
    instrument_variable: str

    def charge_floor(self, tenant_id: str, period_id: str, amount_cents: int) -> str: ...
    def charge_variable(self, tenant_id: str, period_id: str, floor_cents: int, variable_cents: int) -> str: ...


@dataclass
class SingleMandateGateway:
    """Ramo simplificador (billing_single_mandate=true): piso + captura no MESMO preapproval.
    A captura do período é cobrada ajustando o valor do próximo débito para piso + variável.
    Risco: se o PUT falhar depois do débito do ciclo, a captura escorrega um mês — o charge fica
    'submitted' até o webhook de pagamento confirmar."""
    client: MercadoPagoClient
    accounts: dict[str, TenantBillingAccount] = field(default_factory=dict)
    instrument_floor: str = "single_mandate"
    instrument_variable: str = "single_mandate"

    def _account(self, tenant_id: str) -> TenantBillingAccount:
        try:
            return self.accounts[tenant_id]
        except KeyError:
            raise LookupError("tenant sem conta de cobrança configurada") from None

    def charge_floor(self, tenant_id: str, period_id: str, amount_cents: int) -> str:
        acc = self._account(tenant_id)
        if acc.preapproval_id is None:
            r = self.client.create_preapproval(acc.payer_email, amount_cents, "PIZZERIA OS — garantia de auditoria",
                                               f"{tenant_id}:{period_id}")
            acc.preapproval_id = r["id"]
        return acc.preapproval_id

    def charge_variable(self, tenant_id: str, period_id: str, floor_cents: int, variable_cents: int) -> str:
        acc = self._account(tenant_id)
        if acc.preapproval_id is None:
            raise LookupError("mandato inexistente: emita o piso primeiro")
        self.client.update_preapproval_amount(acc.preapproval_id, floor_cents + variable_cents)
        return acc.preapproval_id


@dataclass
class TwoInstrumentGateway:
    """Ramo encarecedor (billing_single_mandate=false): piso como assinatura fixa, captura como
    cobrança avulsa sobre cartão tokenizado em arquivo. Escopo PCI-DSS: o token e o customer_id
    vivem no Mercado Pago; este sistema nunca vê PAN."""
    client: MercadoPagoClient
    accounts: dict[str, TenantBillingAccount] = field(default_factory=dict)
    instrument_floor: str = "subscription"
    instrument_variable: str = "one_off"

    def charge_floor(self, tenant_id: str, period_id: str, amount_cents: int) -> str:
        acc = self.accounts[tenant_id]
        if acc.preapproval_id is None:
            r = self.client.create_preapproval(acc.payer_email, amount_cents, "PIZZERIA OS — garantia de auditoria",
                                               f"{tenant_id}:{period_id}")
            acc.preapproval_id = r["id"]
        return acc.preapproval_id

    def charge_variable(self, tenant_id: str, period_id: str, floor_cents: int, variable_cents: int) -> str:
        acc = self.accounts[tenant_id]
        if not (acc.customer_id and acc.card_token):
            raise LookupError("cartão em arquivo ausente para a cobrança avulsa")
        r = self.client.create_payment(acc.customer_id, acc.card_token, variable_cents,
                                       f"PIZZERIA OS — captura sobre recuperado {period_id}",
                                       idempotency_key=f"{tenant_id}:{period_id}:variavel")
        return str(r["id"])
