-- PIZZERIA OS — Módulo Conciliação e Cobrança · Postgres 15+
-- Invariantes: dinheiro em BIGINT centavos; tenant_id em toda tabela + RLS; recovery_ledger append-only.
-- A aplicação define o tenant por transação:  SET LOCAL app.tenant_id = '<tenant>';

CREATE TABLE platform_fee_rules (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                text NOT NULL,
  channel                  text NOT NULL CHECK (channel IN ('ifood','rappi','proprio')),
  commission_bps           int  NOT NULL CHECK (commission_bps BETWEEN 0 AND 10000),
  commission_base          text NOT NULL CHECK (commission_base IN ('gross','net_of_promo')),
  fixed_fee_cents          bigint NOT NULL CHECK (fixed_fee_cents >= 0),
  promo_platform_share_bps int  NOT NULL CHECK (promo_platform_share_bps BETWEEN 0 AND 10000),
  refund_reverses_commission boolean NOT NULL DEFAULT true,
  valid_from               date NOT NULL,
  valid_to                 date,
  version                  int  NOT NULL,
  UNIQUE (tenant_id, channel, version),
  CHECK (valid_to IS NULL OR valid_to > valid_from)
);
-- vigências não podem se sobrepor por tenant+canal
CREATE EXTENSION IF NOT EXISTS btree_gist;
ALTER TABLE platform_fee_rules ADD CONSTRAINT fee_rules_no_overlap
  EXCLUDE USING gist (tenant_id WITH =, channel WITH =, daterange(valid_from, valid_to, '[)') WITH &&);

CREATE TABLE expected_receivables (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           text NOT NULL,
  order_id            text NOT NULL,
  external_order_ref  text NOT NULL,
  channel             text NOT NULL,
  event_type          text NOT NULL CHECK (event_type IN ('sale','promo','refund')),
  gross_cents         bigint NOT NULL,
  expected_net_cents  bigint NOT NULL,
  fee_rule_version_id uuid NOT NULL REFERENCES platform_fee_rules(id),
  cycle_id            text NOT NULL,
  components          jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ON expected_receivables (tenant_id, external_order_ref);

CREATE TABLE settlement_lines (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            text NOT NULL,
  channel              text NOT NULL,
  external_order_ref   text,            -- NULL = relatório agregado (caminho degradado)
  settlement_cycle_id  text NOT NULL,
  reported_net_cents   bigint NOT NULL,
  line_type            text NOT NULL CHECK (line_type IN ('sale','promo','refund','adjustment')),
  settlement_date      date NOT NULL,
  source_hash          text NOT NULL,
  raw_payload          jsonb NOT NULL,
  UNIQUE (tenant_id, source_hash)
);
CREATE INDEX ON settlement_lines (tenant_id, external_order_ref);

CREATE TABLE bank_transactions (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    text NOT NULL,
  amount_cents bigint NOT NULL,
  value_date   date NOT NULL,
  description  text NOT NULL,
  source_hash  text NOT NULL,
  UNIQUE (tenant_id, source_hash)
);

CREATE TABLE reconciliation_matches (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           text NOT NULL,
  expected_ids        uuid[] NOT NULL,
  settlement_line_ids uuid[] NOT NULL,
  bank_txn_id         uuid REFERENCES bank_transactions(id),
  match_method        text NOT NULL,
  confidence          numeric(4,3) NOT NULL,
  delta_cents         bigint NOT NULL,
  status              text NOT NULL CHECK (status IN ('matched','matched_within_tolerance','divergent')),
  order_ref           text NOT NULL,
  cycle_id            text NOT NULL
);

CREATE TABLE reconciliation_exceptions (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          text NOT NULL,
  type               text NOT NULL,
  amount_cents       bigint NOT NULL,
  order_ref          text,
  cycle_id           text,
  probable_cause     text NOT NULL,
  status             text NOT NULL,
  match_id           uuid REFERENCES reconciliation_matches(id),
  fingerprint        text NOT NULL,
  resolution_history jsonb NOT NULL DEFAULT '[]',
  UNIQUE (tenant_id, fingerprint)
);

CREATE TABLE recovery_ledger (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           text NOT NULL,
  seq                 bigint NOT NULL,
  exception_id        uuid NOT NULL REFERENCES reconciliation_exceptions(id),
  state               text NOT NULL CHECK (state IN ('detected','disputed','confirmed','rejected','billed')),
  amount_cents        bigint NOT NULL CHECK (amount_cents >= 0),
  confirmation_method text CHECK (confirmation_method IN ('auto','manual')),
  attribution_basis   text NOT NULL,
  actor               text NOT NULL,
  evidence            jsonb NOT NULL DEFAULT '{}',
  state_changed_at    timestamptz NOT NULL,
  prev_entry_hash     char(64) NOT NULL,
  entry_hash          char(64) NOT NULL,
  UNIQUE (tenant_id, seq),
  UNIQUE (tenant_id, prev_entry_hash),          -- impede bifurcação da cadeia
  CHECK (state <> 'confirmed' OR confirmation_method IS NOT NULL)
);

CREATE FUNCTION forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'recovery_ledger é append-only'; END $$;
CREATE TRIGGER recovery_ledger_append_only BEFORE UPDATE OR DELETE ON recovery_ledger
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER recovery_ledger_no_truncate BEFORE TRUNCATE ON recovery_ledger
  FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation();

CREATE TABLE attribution_contract (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            text NOT NULL,
  accepted_at          timestamptz NOT NULL,
  accepted_by          text NOT NULL,
  terms_version        text NOT NULL,
  recovered_definition text NOT NULL
);

CREATE TABLE billing_charge (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id             text NOT NULL,
  charge_type           text NOT NULL CHECK (charge_type IN ('floor','variable')),
  period_id             text NOT NULL,
  base_amount_cents     bigint NOT NULL CHECK (base_amount_cents >= 0),
  computed_amount_cents bigint NOT NULL CHECK (computed_amount_cents >= 0),
  cap_applied           boolean NOT NULL,
  breakdown             jsonb NOT NULL DEFAULT '[]',
  gateway_ref           text,
  status                text NOT NULL CHECK (status IN ('draft','submitted','paid','failed')),
  UNIQUE (tenant_id, charge_type, period_id)
  -- ATENÇÃO: arquitetura do braço 'variable' (mandato único vs avulsa) travada pela Incógnita 2.
);

-- RLS: segunda barreira (a primeira é a camada de aplicação)
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['platform_fee_rules','expected_receivables','settlement_lines','bank_transactions',
                           'reconciliation_matches','reconciliation_exceptions','recovery_ledger',
                           'attribution_contract','billing_charge'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format($p$CREATE POLICY tenant_isolation ON %I
                      USING (tenant_id = current_setting('app.tenant_id', true))
                      WITH CHECK (tenant_id = current_setting('app.tenant_id', true))$p$, t);
  END LOOP;
END $$;
