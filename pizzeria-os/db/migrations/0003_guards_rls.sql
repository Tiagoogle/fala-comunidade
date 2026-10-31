-- migration 0003 — guardas de domínio no banco + RLS

-- INV-3: recovery_ledger append-only. UPDATE, DELETE e TRUNCATE falham em nível de banco.
CREATE FUNCTION forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'recovery_ledger é append-only (% proibido)', TG_OP USING ERRCODE = 'insufficient_privilege'; END $$;
CREATE TRIGGER recovery_ledger_no_update BEFORE UPDATE OR DELETE ON recovery_ledger
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER recovery_ledger_no_truncate BEFORE TRUNCATE ON recovery_ledger
  FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation();

-- Encadeamento e trajetória verificados no INSERT: prev_entry_hash deve ser o hash da última entrada do
-- tenant, e a transição de estado deve ser válida para a exceção (CT-L.5 também em nível de banco).
CREATE FUNCTION recovery_ledger_chain_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE last_hash char(64); last_seq bigint; cur_state text;
BEGIN
  SELECT entry_hash, seq INTO last_hash, last_seq FROM recovery_ledger
   WHERE tenant_id = NEW.tenant_id ORDER BY seq DESC LIMIT 1;
  IF last_seq IS NULL THEN
    IF NEW.seq <> 0 OR NEW.prev_entry_hash IS NOT NULL THEN
      RAISE EXCEPTION 'primeira entrada do tenant deve ter seq=0 e prev_entry_hash NULL';
    END IF;
  ELSIF NEW.seq <> last_seq + 1 OR NEW.prev_entry_hash IS DISTINCT FROM last_hash THEN
    RAISE EXCEPTION 'cadeia quebrada: prev_entry_hash não aponta para a última entrada do tenant';
  END IF;

  SELECT state INTO cur_state FROM recovery_ledger
   WHERE tenant_id = NEW.tenant_id AND exception_id = NEW.exception_id ORDER BY seq DESC LIMIT 1;
  IF NOT ((cur_state IS NULL AND NEW.state = 'detected')
       OR (cur_state = 'detected'  AND NEW.state = 'disputed')
       OR (cur_state = 'disputed'  AND NEW.state IN ('confirmed','rejected'))
       OR (cur_state = 'confirmed' AND NEW.state = 'billed')) THEN
    RAISE EXCEPTION 'transição inválida no ledger: % → %', coalesce(cur_state, '∅'), NEW.state
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER recovery_ledger_chain BEFORE INSERT ON recovery_ledger
  FOR EACH ROW EXECUTE FUNCTION recovery_ledger_chain_guard();

-- §9.3: billing_charge exige attribution_contract aceito. O Prompt Mestre propõe CHECK com subquery,
-- que o Postgres rejeita ("cannot use subquery in check constraint"); a guarda equivalente é um trigger.
-- Também exige linha em tenant_feature_flags (§8) e, para 'variavel', a flag da Fase 2 (INV-8).
CREATE FUNCTION billing_charge_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE f tenant_feature_flags%ROWTYPE;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM attribution_contract ac
                  WHERE ac.tenant_id = NEW.tenant_id AND ac.accepted_at IS NOT NULL) THEN
    RAISE EXCEPTION 'billing_charge rejeitada: tenant sem attribution_contract aceito' USING ERRCODE = 'check_violation';
  END IF;
  SELECT * INTO f FROM tenant_feature_flags WHERE tenant_id = NEW.tenant_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'billing_charge rejeitada: tenant sem tenant_feature_flags' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.charge_type = 'variavel' AND NOT f.variable_capture_enabled THEN
    RAISE EXCEPTION 'billing_charge variavel rejeitada: variable_capture_enabled=false' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER billing_charge_attribution_guard BEFORE INSERT OR UPDATE ON billing_charge
  FOR EACH ROW EXECUTE FUNCTION billing_charge_guard();

-- INV-2: RLS como segunda barreira. A aplicação define: SET LOCAL app.tenant_id = '<tenant>';
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['tenants','platform_fee_rules','expected_receivables','settlement_lines','bank_transactions',
                           'reconciliation_matches','reconciliation_exceptions','recovery_ledger','attribution_contract',
                           'billing_charge','tenant_feature_flags','tenant_feature_flag_audit',
                           'tenant_onboarding_state','integration_tokens'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format($p$CREATE POLICY tenant_isolation ON %I
                      USING (tenant_id = current_setting('app.tenant_id', true))
                      WITH CHECK (tenant_id = current_setting('app.tenant_id', true))$p$, t);
  END LOOP;
END $$;
