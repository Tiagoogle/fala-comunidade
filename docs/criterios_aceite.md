# Critérios de aceite (spec Tabela 23) → evidência

Rodar: `cd backend && python -m pytest -v`. "Código" = verificado por teste automatizado; "Campo" = exige
verificação com pessoas reais antes da Fase 4 e **não** está coberto aqui.

| # | Critério | Cobertura | Onde |
|---|---|---|---|
| 1 | Não inventa informações | Código | `test_c01_*` — sem base aprovada → recusa + encaminhamento; resposta factual cita fonte/data; resumo alucinado é descartado pela guarda de saída e auditado |
| 2 | Não promete prazos sem autorização | Código | `test_c02_*`; guarda bloqueia promessa/prazo/número não fundamentado (`test_guarda_*`) |
| 3 | Oferece atendimento humano | Código | `test_c03_*`, `test_d13_*` — detectado em qualquer etapa, sem reter |
| 4 | Registra protocolos corretamente | Código | `test_c04_*` — sequencial por ano/UF, único, idempotente no sync offline |
| 5 | Preserva a mensagem original | Código | `test_c05_*` — trava ORM de imutabilidade + hash SHA-256 |
| 6 | Permite correções | Código | `test_c06_*` — adendos versionados; mudança de prioridade força revisão |
| 7 | Trata anexos com segurança | Código | `test_c07_*` — cifra em repouso, hash, acesso só revisor com motivo, auditado |
| 8 | Encaminha emergências | Código | `test_c08_*`, `test_d04_*` — detecção léxica antes do LLM, fila P1, só sai por decisão humana |
| 9 | Funciona em dispositivos móveis | **Parcial** | PWA testada em 420px (Playwright). Falta matriz de aparelhos reais e simples. |
| 10 | Estados de erro e offline | Código + E2E | `test_c10_*`; E2E offline → online sem duplicar |
| 11 | Acessibilidade | **Parcial** | Rótulos, foco visível, `aria-live`, alvos ≥44px, A+, sim/não. Falta auditoria WCAG/eMAG e testes com PCD. |
| 12 | Registra eventos de auditoria | Código | `test_c12_*` — cadeia de hash detecta adulteração |
| 13 | Permite revisão humana | Código | `test_c13_*` — justificativa obrigatória; quem registrou não valida |
| 14 | Evita decisões só por IA | Código | `test_c14_*` — encaminhamento bloqueado sem validação; modelo não rebaixa prioridade |
| 15 | Protege dados pessoais | Código | `test_c15_*` — anonimato estrutural, contato cifrado com acesso motivado, recusa descarta relato |
| 16 | Informação compreensível | **Campo** | Textos seguem a spec; validação com público de baixa alfabetização é da Fase 3. |
| 17 | Testes de viés e segurança | Código (inicial) | `test_c17_*`, `test_adversarial.py`. A bateria precisa de amostras reais de fala regional. |
| 18 | Desligamento seguro | Código | `test_c18_*` — total, LLM, triagem, base; só governança, com motivo auditado |
| 19 | Canais não digitais operantes | **Campo** | Fora do software: checklist por território. |
