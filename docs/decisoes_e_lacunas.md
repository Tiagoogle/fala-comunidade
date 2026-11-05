# Decisões de desenho, limitações e pendências

## Decisões

1. **Fluxo determinístico, LLM restrito.** O modelo só faz resumo e sugestão de triagem. Protocolo, prazo,
   emergência, escalonamento, consentimento e encerramento são código. Motivo: §7.3 ("o prompt sozinho não é
   controle de segurança") e risco C3/C4. Custo: conversa menos fluida que um chatbot livre.
2. **"O mais protetor vence."** A prioridade final é a mais alta entre regras e modelo; o modelo nunca rebaixa.
   Termos de risco negados ("não teve acidente, mas quase…") viram P2 com revisão, não descarte.
3. **Código de consulta para todos**, não só anônimos: o número de protocolo é sequencial e enumerável.
   Resposta idêntica para "inexistente" e "código errado"; limite de tentativas.
4. **Respostas factuais nunca são geradas pelo modelo.** Vêm do texto aprovado, com fonte e data.
5. **Emergência sem consentimento prévio** usa a base legal de proteção da vida (LGPD art. 7º, VII).
   *Depende de parecer jurídico (J1).*
6. **Offline:** o código de consulta é gerado no aparelho (a pessoa sai com ele na hora); o protocolo chega
   no sync. Após o envio, o aparelho apaga o conteúdo e guarda só o protocolo.
7. **Direitos do titular sem nova credencial:** protocolo + código de consulta autenticam o titular,
   inclusive anônimo, e compartilham o limite de tentativas da consulta de status. Pedidos de eliminação
   **nunca** apagam conteúdo automaticamente: vão ao DPO, porque pode haver obrigação de guarda (UC-10).
8. **Descarte não quebra a imutabilidade:** só `retention.py` pode trocar o original por um marcador,
   mantendo o `hash_original` e registrando o evento `descarte`. Qualquer outra tentativa continua
   bloqueada.
9. **Fallback do Claude:** `fallbacks="default"` (server-side) em recusas; qualquer falha restante cai no modo
   determinístico e é auditada (`llm_falha`). O registro nunca depende do provedor.

## Limitações conhecidas (honestas)

- **Detecção léxica tem limite.** Pega a maioria dos casos de risco imediato em português regional, mas não
  substitui escuta. Falsos negativos possíveis em descrições indiretas. Mitigação parcial: pergunta explícita
  de risco em temas sensíveis e checagem no aparelho offline.
- **Horas úteis** são aproximadas por horas corridas no cálculo de prazo-alvo. Calendário corporativo pendente.
- **ASR não implementado:** áudio é guardado como original, e a transcrição é feita/confirmada pelo agente de
  campo. Enquanto não houver confirmação, o encaminhamento fica bloqueado.
- **Autenticação por chave** é só para piloto técnico. Produção exige SSO, MFA e revisão de permissões.
- **Cifra no aparelho**: a chave AES fica no próprio navegador (não exportável). Protege contra extração
  casual do banco, não contra um aparelho comprometido.
- **Integrações** CRM/ouvidoria/ERP são stubs com outbox (fora do escopo do MVP).
- **Uma única máquina no Fly** (SQLite em volume): sem alta disponibilidade até migrar para Postgres.
- **Indicadores** calculados em memória; para volume real, usar visões SQL materializadas.

## Bloqueios antes do piloto (cap. 17)

| Pergunta | Por que bloqueia |
|---|---|
| J1/J4 — base legal por modo de identificação; anonimato e código | Define consentimento, retenção e a regra de emergência |
| J2/J3 — prazos de guarda e exclusão | A rotina de descarte existe (`escuta/retention.py`), mas sem prazos aprovados nada é descartado |
| J7 — política antirretaliação formal | O fluxo D-11 promete encaminhamento à Ouvidoria |
| O2/O3 — plantão P1 e lista nominal de revisores sigilosos | Sem isso, a fila P1 e a rota sigilosa não têm dono real |
| C2 — povos indígenas/tradicionais no território-piloto | Se houver, exige consulta prévia (OIT 169) antes de operar |
| P2 — conteúdo aprovado para a base | Base atual só explica o canal; sem conteúdo operacional, quase toda pergunta vira encaminhamento |
