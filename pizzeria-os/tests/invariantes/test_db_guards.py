"""Guardas em nível de banco contra as migrations reais (CT-L.3, CT-L.4, CT-B.5, INV-2, INV-3).

Requer DATABASE_URL apontando para um Postgres descartável. Sem ele, os testes são pulados
localmente — mas com REQUIRE_DB=1 (CI) a ausência do banco FALHA a pipeline.
"""
import os
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
URL = os.environ.get("DATABASE_URL")
MIGRATIONS = sorted((Path(__file__).resolve().parents[2] / "db" / "migrations").glob("*.sql"))

if not URL:
    if os.environ.get("REQUIRE_DB") == "1":
        raise RuntimeError("REQUIRE_DB=1 e DATABASE_URL ausente: guardas de banco não podem ser puladas no CI")
    pytest.skip("DATABASE_URL ausente", allow_module_level=True)

Z64 = "0" * 64


@pytest.fixture
def db():
    conn = psycopg.connect(URL, autocommit=True)
    conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    for m in MIGRATIONS:
        conn.execute(m.read_text(encoding="utf-8"))
    conn.execute("DROP ROLE IF EXISTS pz_app; CREATE ROLE pz_app; GRANT USAGE ON SCHEMA public TO pz_app; "
                 "GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public TO pz_app; "
                 "GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO pz_app;")
    yield conn
    conn.close()


def as_tenant(conn, tenant):
    conn.execute("SET ROLE pz_app")
    conn.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant,))


def seed(conn, tenant="pz-a", contract=True, flags=True, cnpj="11222333000181"):
    as_tenant(conn, tenant)
    conn.execute("INSERT INTO tenants VALUES (%s,'P',%s,'Rua','Maria','m@p.test',now())", (tenant, cnpj))
    if flags:
        conn.execute("INSERT INTO tenant_feature_flags (tenant_id) VALUES (%s)", (tenant,))
    if contract:
        conn.execute("INSERT INTO attribution_contract (tenant_id, accepted_at, accepted_by, accepted_ip, terms_version, "
                     "recovered_definition) VALUES (%s, now(), 'Maria', '200.1.1.1', 'v1', repeat('x', 50))", (tenant,))
    exc = conn.execute("INSERT INTO reconciliation_exceptions (tenant_id,type,amount_cents,probable_cause,status,fingerprint)"
                       " VALUES (%s,'taxa_divergente',398,'promo','open','f1') RETURNING id", (tenant,)).fetchone()[0]
    return exc


def ledger_insert(conn, tenant, exc, seq, state, prev, h, method=None):
    conn.execute("INSERT INTO recovery_ledger (tenant_id,seq,exception_id,state,amount_cents,confirmation_method,"
                 "attribution_basis,actor,state_changed_at,prev_entry_hash,entry_hash) "
                 "VALUES (%s,%s,%s,%s,398,%s,'m','sys',now(),%s,%s)", (tenant, seq, exc, state, method, prev, h))


def test_ct_l_3_update_rejected(db):
    exc = seed(db)
    ledger_insert(db, "pz-a", exc, 0, "detected", None, "1" * 64)
    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"):
        db.execute("UPDATE recovery_ledger SET amount_cents = 1")


def test_ct_l_4_delete_and_truncate_rejected(db):
    exc = seed(db)
    ledger_insert(db, "pz-a", exc, 0, "detected", None, "1" * 64)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("DELETE FROM recovery_ledger")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("TRUNCATE recovery_ledger")


def test_ledger_chain_and_transition_enforced_by_db(db):
    exc = seed(db)
    ledger_insert(db, "pz-a", exc, 0, "detected", None, "1" * 64)
    with pytest.raises(psycopg.errors.RaiseException, match="cadeia quebrada"):
        ledger_insert(db, "pz-a", exc, 1, "disputed", Z64, "2" * 64)
    with pytest.raises(psycopg.errors.CheckViolation, match="transição inválida"):
        ledger_insert(db, "pz-a", exc, 1, "billed", "1" * 64, "2" * 64)
    ledger_insert(db, "pz-a", exc, 1, "disputed", "1" * 64, "2" * 64)


def test_ct_b_5_billing_without_contract_rejected(db):
    seed(db, contract=False)
    with pytest.raises(psycopg.errors.CheckViolation, match="attribution_contract"):
        db.execute("INSERT INTO billing_charge (tenant_id,charge_type,period_id,base_amount_cents,computed_amount_cents,"
                   "cap_applied,status) VALUES ('pz-a','piso','2026-11',12900,12900,false,'draft')")


def test_billing_with_contract_ok_but_variable_needs_flag(db):
    seed(db)
    db.execute("INSERT INTO billing_charge (tenant_id,charge_type,period_id,base_amount_cents,computed_amount_cents,"
               "cap_applied,status) VALUES ('pz-a','piso','2026-11',12900,12900,false,'draft')")
    with pytest.raises(psycopg.errors.CheckViolation, match="variable_capture_enabled"):
        db.execute("INSERT INTO billing_charge (tenant_id,charge_type,period_id,base_amount_cents,computed_amount_cents,"
                   "cap_applied,status) VALUES ('pz-a','variavel','2026-11',1000,250,false,'draft')")


def test_billing_without_flags_row_rejected(db):
    seed(db, flags=False)
    with pytest.raises(psycopg.errors.CheckViolation, match="tenant_feature_flags"):
        db.execute("INSERT INTO billing_charge (tenant_id,charge_type,period_id,base_amount_cents,computed_amount_cents,"
                   "cap_applied,status) VALUES ('pz-a','piso','2026-11',12900,12900,false,'draft')")


def test_inv2_rls_isolates_tenants(db):
    seed(db, "pz-a")
    as_tenant(db, "pz-b")
    assert db.execute("SELECT count(*) FROM reconciliation_exceptions").fetchone()[0] == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("INSERT INTO reconciliation_exceptions (tenant_id,type,amount_cents,probable_cause,status,fingerprint)"
                   " VALUES ('pz-a','taxa_divergente',1,'x','open','f9')")


def test_onboarding_order_and_integration_guard(db):
    seed(db, contract=False)
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("INSERT INTO tenant_onboarding_state (tenant_id, integrations_at) VALUES ('pz-a', now())")
    with pytest.raises(psycopg.errors.CheckViolation, match="attribution_contract"):
        db.execute("INSERT INTO integration_tokens (tenant_id, provider, access_token_enc) VALUES ('pz-a','ifood','\\x00')")


def test_fee_rule_overlap_rejected(db):
    seed(db)
    db.execute("INSERT INTO platform_fee_rules (tenant_id,channel,commission_bps,commission_base,fixed_fee_cents,"
               "promo_platform_share_bps,valid_from,version) VALUES ('pz-a','ifood',2300,'gross',99,5000,'2026-01-01',1)")
    with pytest.raises(psycopg.errors.ExclusionViolation):
        db.execute("INSERT INTO platform_fee_rules (tenant_id,channel,commission_bps,commission_base,fixed_fee_cents,"
                   "promo_platform_share_bps,valid_from,version) VALUES ('pz-a','ifood',2500,'gross',99,5000,'2026-06-01',2)")


def test_flag_changes_audited_by_trigger(db):
    seed(db)
    db.execute("SELECT set_config('app.actor', 'admin@pz', false)")
    db.execute("UPDATE tenant_feature_flags SET settlement_itemized = true WHERE tenant_id = 'pz-a'")
    rows = db.execute("SELECT flag, old_value, new_value, changed_by FROM tenant_feature_flag_audit "
                      "WHERE old_value IS NOT NULL").fetchall()
    assert rows == [("settlement_itemized", False, True, "admin@pz")]
