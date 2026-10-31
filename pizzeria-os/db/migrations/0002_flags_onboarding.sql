-- migration 0002 — feature flags por tenant (§8), onboarding (§9), tokens cifrados

CREATE TABLE tenant_feature_flags (
  tenant_id                text PRIMARY KEY REFERENCES tenants,
  confirmation_method_auto boolean NOT NULL DEFAULT false,  -- Incógnita 1
  billing_single_mandate   boolean NOT NULL DEFAULT false,  -- Incógnita 2
  settlement_itemized      boolean NOT NULL DEFAULT false,  -- Incógnita 3
  variable_capture_enabled boolean NOT NULL DEFAULT false   -- Fase 2 do roadmap
);

CREATE TABLE tenant_feature_flag_audit (
  id         bigserial PRIMARY KEY,
  tenant_id  text NOT NULL REFERENCES tenants,
  flag       text NOT NULL,
  old_value  boolean,
  new_value  boolean NOT NULL,
  changed_by text NOT NULL,
  changed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON tenant_feature_flag_audit (tenant_id, changed_at);

-- auditoria automática: nenhuma mudança de flag escapa do log, mesmo via SQL direto
CREATE FUNCTION audit_feature_flags() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE f text; o boolean; n boolean; who text := coalesce(current_setting('app.actor', true), current_user);
BEGIN
  FOREACH f IN ARRAY ARRAY['confirmation_method_auto','billing_single_mandate','settlement_itemized','variable_capture_enabled'] LOOP
    EXECUTE format('SELECT ($1).%I, ($2).%I', f, f) INTO o, n USING OLD, NEW;
    IF TG_OP = 'INSERT' OR o IS DISTINCT FROM n THEN
      INSERT INTO tenant_feature_flag_audit (tenant_id, flag, old_value, new_value, changed_by)
      VALUES (NEW.tenant_id, f, CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE o END, n, who);
    END IF;
  END LOOP;
  RETURN NEW;
END $$;
CREATE TRIGGER tenant_feature_flags_audit AFTER INSERT OR UPDATE ON tenant_feature_flags
  FOR EACH ROW EXECUTE FUNCTION audit_feature_flags();

CREATE TABLE tenant_onboarding_state (
  tenant_id                text PRIMARY KEY REFERENCES tenants,
  tenant_registered_at     timestamptz NOT NULL DEFAULT now(),
  fee_contract_at          timestamptz,
  attribution_accepted_at  timestamptz,
  integrations_at          timestamptz,
  calibration_done_at      timestamptz,
  -- ordem sequencial em nível de banco: nenhuma etapa sem a anterior
  CHECK (fee_contract_at         IS NULL OR tenant_registered_at    IS NOT NULL),
  CHECK (attribution_accepted_at IS NULL OR fee_contract_at         IS NOT NULL),
  CHECK (integrations_at         IS NULL OR attribution_accepted_at IS NOT NULL),
  CHECK (calibration_done_at     IS NULL OR integrations_at         IS NOT NULL)
);

-- Etapa 3 só pode ser marcada se o contrato existir de fato
CREATE FUNCTION onboarding_attribution_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.attribution_accepted_at IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM attribution_contract ac WHERE ac.tenant_id = NEW.tenant_id AND ac.accepted_at IS NOT NULL) THEN
    RAISE EXCEPTION 'onboarding: etapa 3 exige attribution_contract aceito' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tenant_onboarding_attribution_guard BEFORE INSERT OR UPDATE ON tenant_onboarding_state
  FOR EACH ROW EXECUTE FUNCTION onboarding_attribution_guard();

CREATE TABLE integration_tokens (
  tenant_id         text NOT NULL REFERENCES tenants,
  provider          text NOT NULL CHECK (provider IN ('ifood','mercadopago')),
  access_token_enc  bytea NOT NULL,     -- cifrado na aplicação (Fernet); o banco nunca vê o token em claro
  refresh_token_enc bytea,
  expires_at        timestamptz,
  updated_at        timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, provider)
);

-- Etapa 4 proibida sem aceite (guarda em nível de banco)
CREATE FUNCTION integration_tokens_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM attribution_contract ac WHERE ac.tenant_id = NEW.tenant_id AND ac.accepted_at IS NOT NULL) THEN
    RAISE EXCEPTION 'integrações proibidas sem attribution_contract aceito' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER integration_tokens_attribution_guard BEFORE INSERT ON integration_tokens
  FOR EACH ROW EXECUTE FUNCTION integration_tokens_guard();
