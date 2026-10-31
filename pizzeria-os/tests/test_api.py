import io

from fastapi.testclient import TestClient

from conciliacao import api

A = {"X-Admin-Token": "dev-admin"}


def test_end_to_end_http_flow():
    c = TestClient(api.app)
    t = "pizzaria-http"
    H = {"X-Tenant-Id": t}
    assert c.post("/onboarding/register", json={"tenant_id": t, "name": "P", "cnpj": "11.444.777/0001-61",
                  "address": "Rua", "legal_representative": "Ana", "contact_email": "a@p.test"}).status_code == 201
    assert c.post("/onboarding/attribution", headers=H, json={"terms_version": "v1", "accepted_by": "Ana"}).status_code == 409
    assert c.post("/onboarding/fee-contract", headers=H, json={"commission_bps": 2300, "fixed_fee_cents": 99,
                  "promo_platform_share_bps": 5000, "onboarding_date": "2026-01-01"}).status_code == 200
    assert c.post("/onboarding/fee-contract", headers=H, json={"commission_bps": 23.5, "fixed_fee_cents": 99,
                  "promo_platform_share_bps": 5000}).status_code == 422                       # INV-1 na borda
    assert c.post("/onboarding/attribution", headers=H, json={"terms_version": "v1", "accepted_by": "Ana"}).status_code == 200
    assert c.post("/onboarding/integrations", headers=H, json={"ifood_token": "x", "mercadopago_token": "y"}).status_code == 200
    c.post("/orders/events", headers=H, json=[{"order_id": "o1", "external_order_ref": "#IF-1", "channel": "ifood",
           "event_type": "sale", "gross_cents": 6890, "promo_discount_cents": 796, "occurred_on": "2026-10-20"}])
    csv = "pedido;tipo;valor_liquido;data_repasse\nIF-1;venda;44,10;26/10/2026\n"
    assert c.post("/settlements/ifood/csv", headers=H, files={"file": ("r.csv", io.BytesIO(csv.encode()))}).json()["accepted"] == 1
    assert c.post("/reconcile", headers=H).status_code == 409                                  # ainda em onboarding
    cal = c.post("/onboarding/calibrate", headers=H, json={"approve": True, "actor": "Ana"}).json()
    assert cal["active"] and cal["summary"]["metrics"]["exceptions_by_type"] == {"taxa_divergente": 1}

    c.post("/cycles/close", headers=H, json={"cycle_ids": ["ifood:2026-10-19"]})
    assert c.post("/reconcile", headers=H).status_code == 200
    (exc,) = c.get("/exceptions", headers=H).json()
    assert exc["amount_cents"] == 398 and exc["ledger_state"] == "detected"
    assert c.post(f"/exceptions/{exc['id']}/dispute", headers=H, json={"actor": "ops", "protocol": "P-1"}).status_code == 200
    assert c.post("/ledger/confirmation-loop", headers=H).json() == {"confirmed": [], "mode": "manual"}
    r = c.post(f"/exceptions/{exc['id']}/confirm", headers=H, json={"amount_cents": 398, "attested_by": "Ana",
               "evidence_ref": "extrato 02/11"})
    assert r.json()["confirmation_method"] == "manual"
    trail = c.get(f"/exceptions/{exc['id']}/trail", headers=H).json()
    assert [x["state"] for x in trail["ledger"]] == ["detected", "disputed", "confirmed"] and trail["chain_valid"]

    p = c.get("/billing/2026-11/variavel/preview", headers=H).json()
    assert p["computed_cents"] == 100 and len(p["blockers"]) == 3
    assert c.post("/billing/2026-11/piso", headers=H).json()["computed_cents"] == 12_900

    assert c.put(f"/admin/tenants/{t}/flags/settlement_itemized", headers=A,
                 json={"value": True, "changed_by": "admin", "evidence": "relatório real com id_pedido"}).status_code == 200
    assert c.put(f"/admin/tenants/{t}/flags/settlement_itemized", headers={"X-Admin-Token": "x"},
                 json={"value": True, "changed_by": "a", "evidence": "xxxxxxxxxxxx"}).status_code == 403
    assert len(c.get(f"/admin/tenants/{t}/flags", headers=A).json()["audit"]) == 1

    assert c.get("/exceptions", headers={"X-Tenant-Id": "outra"}).status_code == 404
    assert "Exceções e trilha" in c.get("/dashboard").text


def test_degraded_flow_via_queue():
    c = TestClient(api.app)
    t = "pizzaria-agregada"
    H = {"X-Tenant-Id": t}
    c.post("/onboarding/register", json={"tenant_id": t, "name": "P", "cnpj": "11.222.333/0001-81", "address": "R",
           "legal_representative": "B", "contact_email": "b@p.test"})
    c.post("/onboarding/fee-contract", headers=H, json={"commission_bps": 2300, "fixed_fee_cents": 99,
           "promo_platform_share_bps": 5000, "onboarding_date": "2026-01-01"})
    c.post("/onboarding/attribution", headers=H, json={"terms_version": "v1", "accepted_by": "B"})
    c.post("/onboarding/integrations", headers=H, json={"ifood_token": "x", "mercadopago_token": "y"})
    c.post("/onboarding/calibrate", headers=H, json={"approve": True, "actor": "B"})
    c.post("/orders/events", headers=H, json=[
        {"order_id": "a", "external_order_ref": "A1", "channel": "ifood", "event_type": "sale", "gross_cents": 5000, "occurred_on": "2026-10-20"},
        {"order_id": "b", "external_order_ref": "A2", "channel": "ifood", "event_type": "sale", "gross_cents": 10000, "occurred_on": "2026-10-21"}])
    agg = "valor_liquido;data_repasse\n113,52;26/10/2026\n"
    c.post("/settlements/ifood/csv?aggregate=true", headers=H, files={"file": ("a.csv", io.BytesIO(agg.encode()))})
    c.post("/cycles/close", headers=H, json={"cycle_ids": ["ifood:2026-10-19"]})
    assert c.post("/reconcile", headers=H).json()["metrics"]["subset_sum_requested"] == 1
    assert c.post("/jobs/drain", headers=A).json()["executed"] == 1
    r = c.post("/reconcile", headers=H).json()
    assert r["metrics"]["auto_match_rate"] == 1.0 and r["metrics"]["exceptions_by_type"] == {}
