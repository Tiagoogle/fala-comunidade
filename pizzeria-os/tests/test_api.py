import io

from fastapi.testclient import TestClient

from conciliacao import api

H = {"X-Tenant-Id": "pizzaria-api"}


def test_end_to_end_flow():
    c = TestClient(api.app)
    assert c.post("/fee-rules", headers=H, json={
        "channel": "ifood", "commission_bps": 2300, "fixed_fee_cents": 99, "promo_platform_share_bps": 5000,
        "valid_from": "2026-01-01", "version": 1}).status_code == 201
    r = c.post("/orders/events", headers=H, json=[
        {"order_id": "o1", "external_order_ref": "#if-1", "channel": "ifood", "event_type": "sale",
         "gross_cents": 6890, "promo_discount_cents": 796, "occurred_on": "2026-10-20"},
        {"order_id": "o2", "external_order_ref": "IF-2", "channel": "ifood", "event_type": "sale",
         "gross_cents": 5000, "occurred_on": "2026-10-21"},
    ])
    assert r.status_code == 201, r.text
    csv = "pedido;tipo;valor_liquido;data_repasse\nIF-1;venda;44,10;26/10/2026\nIF-9;venda;12,00;26/10/2026\n"
    r = c.post("/settlements/ifood/csv", headers=H, files={"file": ("rep.csv", io.BytesIO(csv.encode()))})
    assert r.json()["accepted"] == 2
    c.post("/cycles/close", headers=H, json={"cycle_ids": ["ifood:2026-10-19"]})
    r = c.post("/reconcile", headers=H).json()
    assert r["metrics"]["exceptions_by_type"] == {"taxa_divergente": 1, "venda_sem_repasse": 1, "repasse_sem_venda": 1}
    assert any("Passe 4" in b for b in r["blocked"])

    excs = {e["type"]: e for e in c.get("/exceptions", headers=H).json()}
    promo = excs["taxa_divergente"]
    assert promo["amount_cents"] == 398 and promo["ledger_state"] == "detected"

    # idempotência
    assert c.post("/reconcile", headers=H).json()["new_exceptions"] == 0

    assert c.post(f"/exceptions/{promo['id']}/dispute", headers=H, json={"actor": "ops", "protocol": "P-1"}).status_code == 200
    assert c.post("/ledger/auto-confirm", headers=H).status_code == 409   # Incógnita 1 aberta
    r = c.post(f"/exceptions/{promo['id']}/confirm", headers=H,
               json={"amount_cents": 398, "attested_by": "dono", "evidence_ref": "extrato 02/11"})
    assert r.json()["confirmation_method"] == "manual"
    assert c.get("/ledger/verify", headers=H).json()["valid"]

    p = c.get("/billing/2026-10/variable/preview", headers=H).json()
    assert p["computed_cents"] == 100 and len(p["blockers"]) >= 3
    assert c.post("/billing/2026-10/floor", headers=H).json()["computed_cents"] == 12_900

    # isolamento: outro tenant não enxerga nada
    assert c.get("/exceptions", headers={"X-Tenant-Id": "outra"}).json() == []
    assert c.post(f"/exceptions/{promo['id']}/dispute", headers={"X-Tenant-Id": "outra"},
                  json={"actor": "x", "protocol": "y"}).status_code == 404


def test_gates_endpoint():
    c = TestClient(api.app)
    g = c.get("/gates").json()
    assert set(g) == {"ifood_traceable_adjustment", "gateway_variable_amount", "settlement_itemized"}
    assert c.put("/gates/settlement_itemized", json={"branch": "simplifies", "evidence": "x", "resolved_on": "2026-11-01"}).status_code == 422
