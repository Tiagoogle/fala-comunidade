-- PIZZERIA OS · Conciliação e Cobrança · migration 0001 — modelo de dados (Prompt Mestre §5)
-- INV-1: dinheiro em BIGINT centavos. INV-2: tenant_id em toda tabela + RLS (migration 0003).
-- Índices (tenant_id, cycle_id) / (tenant_id, external_order_ref) / (tenant_id, status) criados
-- em toda tabela que possui a coluna correspondente.

CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE tenants (
  tenant_id            text PRIMARY KEY CHECK (tenant_id ~ '^[a-z0-9-]{3,64}$'),
  name                 text NOT NULL,
  cnpj                 char(14) NOT NULL UNIQUE CHECK (cnpj ~ '^[0-9]{14}$'),
  address              text NOT NULL,
  legal_representative text NOT NULL,
  contact_email        text NOT NULL,
  created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE platform_fee_rules (
  id                         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                  text NOT NULL REFERENCES tenants,
  channel                    text NOT NULL CHECK (channel IN ('ifood','rappi','proprio')),
  commission_bps             int  NOT NULL CHECK (commission_bps BETWEEN 0 AND 10000),
  commission_base            text NOT NULL CHECK (commission_base IN ('gross','net_of_promo')),
  fixed_fee_cents            bigint NOT NULL CHECK (fixed_fee_cents >= 0),
  promo_platform_share_bps   int  NOT NULL CHECK (promo_platform_share_bps BETWEEN 0 AND 10000),
  refund_reverses_commission boolean NOT NULL DEFAULT true,
  valid_from                 date NOT NULL,
  valid_to                   date,
  version                    int  NOT NULL CHECK (version >= 1),
  UNIQUE (tenant_id, channel, version),
  CHECK (valid_to IS NULL OR valid_to > valid_from),
  -- INV-5: vigências não se sobrepõem por tenant+canal
  EXCLUDE USING gist (tenant_id WITH =, channel WITH =, daterange(valid_from, valid_to, '[)') WITH &&)
);

CREATE TABLE expected_receivables (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           text NOT NULL REFERENCES tenants,
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
CREATE INDEX ON expected_receivables (tenant_id, cycle_id);
CREATE INDEX ON expected_receivables (tenant_id, external_order_ref);

CREATE TABLE settlement_lines (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           text NOT NULL REFERENCES tenants,
  channel             text NOT NULL,
  external_order_ref  text,                         -- NULL = relatório agregado
  settlement_cycle_id text NOT NULL,
  reported_net_cents  bigint NOT NULL,
  line_type           text NOT NULL CHECK (line_type IN ('sale','promo','refund','adjustment')),
  settlement_date     date NOT NULL,
  source_hash         text NOT NULL,
  raw_payload         jsonb NOT NULL,
  UNIQUE (tenant_id, source_hash)
);
CREATE INDEX ON settlement_lines (tenant_id, settlement_cycle_id);
CREATE INDEX ON settlement_lines (tenant_id, external_order_ref);

CREATE TABLE bank_transactions (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    text NOT NULL REFERENCES tenants,
  amount_cents bigint NOT NULL,
  value_date   date NOT NULL,
  description  text NOT NULL,
  source_hash  text NOT NULL,
  UNIQUE (tenant_id, source_hash)                   -- CT-0.2: reimportar não duplica
);
CREATE INDEX ON bank_transactions (tenant_id, value_date);

CREATE TABLE reconciliation_matches (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           text NOT NULL REFERENCES tenants,
  expected_ids        uuid[] NOT NULL,
  settlement_line_ids uuid[] NOT NULL,
  bank_txn_id         uuid REFERENCES bank_transactions(id),
  match_method        text NOT NULL CHECK (match_method IN ('key_event','key_order_aggregate','key_loose','subset_sum','bank')),
  confidence          numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  delta_cents         bigint NOT NULL,
  status              text NOT NULL CHECK (status IN ('matched','matched_within_tolerance','divergent')),
  external_order_ref  text NOT NULL,
  cycle_id            text NOT NULL
);
CREATE INDEX ON reconciliation_matches (tenant_id, cycle_id);
CREATE INDEX ON reconciliation_matches (tenant_id, external_order_ref);
CREATE INDEX ON reconciliation_matches (tenant_id, status);

CREATE TABLE reconciliation_exceptions (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          text NOT NULL REFERENCES tenants,
  type               text NOT NULL CHECK (type IN ('taxa_divergente','venda_sem_repasse','repasse_sem_venda',
                                                   'antecipacao','diferenca_caixa','deriva_sistematica')),
  amount_cents       bigint NOT NULL,
  external_order_ref text,
  cycle_id           text,
  probable_cause     text NOT NULL,
  status             text NOT NULL CHECK (status IN ('open','human_queue','in_recovery','resolved','dismissed')),
  match_id           uuid REFERENCES reconciliation_matches(id),
  fingerprint        text NOT NULL,
  resolution_history jsonb NOT NULL DEFAULT '[]',
  UNIQUE (tenant_id, fingerprint)
);
CREATE INDEX ON reconciliation_exceptions (tenant_id, cycle_id);
CREATE INDEX ON reconciliation_exceptions (tenant_id, external_order_ref);
CREATE INDEX ON reconciliation_exceptions (tenant_id, status);

CREATE TABLE recovery_ledger (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           text NOT NULL REFERENCES tenants,
  seq                 bigint NOT NULL CHECK (seq >= 0),
  exception_id        uuid NOT NULL REFERENCES reconciliation_exceptions(id),
  state               text NOT NULL CHECK (state IN ('detected','disputed','confirmed','rejected','billed')),
  amount_cents        bigint NOT NULL CHECK (amount_cents >= 0),
  confirmation_method text CHECK (confirmation_method IN ('auto','manual')),
  attribution_basis   text NOT NULL,
  actor               text NOT NULL,
  evidence            jsonb NOT NULL DEFAULT '{}',
  state_changed_at    timestamptz NOT NULL,
  prev_entry_hash     char(64),                     -- NULL apenas na primeira entrada do tenant
  entry_hash          char(64) NOT NULL,
  UNIQUE (tenant_id, seq),
  UNIQUE (tenant_id, prev_entry_hash),              -- impede bifurcação da cadeia
  UNIQUE (entry_hash),
  CHECK (state <> 'confirmed' OR confirmation_method IS NOT NULL),
  CHECK ((seq = 0) = (prev_entry_hash IS NULL))
);
CREATE UNIQUE INDEX recovery_ledger_single_genesis ON recovery_ledger (tenant_id) WHERE prev_entry_hash IS NULL;
CREATE INDEX ON recovery_ledger (tenant_id, exception_id, seq);
CREATE INDEX ON recovery_ledger (tenant_id, state);

CREATE TABLE attribution_contract (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            text NOT NULL REFERENCES tenants,
  accepted_at          timestamptz NOT NULL,
  accepted_by          text NOT NULL,
  accepted_ip          inet NOT NULL,
  terms_version        text NOT NULL,
  recovered_definition text NOT NULL CHECK (length(recovered_definition) >= 40)
);
CREATE INDEX ON attribution_contract (tenant_id);

CREATE TABLE billing_charge (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id             text NOT NULL REFERENCES tenants,
  charge_type           text NOT NULL CHECK (charge_type IN ('piso','variavel')),
  period_id             text NOT NULL CHECK (period_id ~ '^[0-9]{4}-[0-9]{2}$'),
  base_amount_cents     bigint NOT NULL CHECK (base_amount_cents >= 0),
  computed_amount_cents bigint NOT NULL CHECK (computed_amount_cents >= 0),
  cap_applied           boolean NOT NULL,
  instrument            text CHECK (instrument IN ('single_mandate','subscription','one_off')),
  breakdown             jsonb NOT NULL DEFAULT '[]',
  gateway_ref           text,
  status                text NOT NULL CHECK (status IN ('draft','submitted','paid','failed')),
  UNIQUE (tenant_id, charge_type, period_id)
);
CREATE INDEX ON billing_charge (tenant_id, status);
