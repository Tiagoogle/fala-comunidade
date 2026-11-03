# Fala Comunidade — Escuta+

Implementação do **MVP seguro (§18.5)** da *Especificação do Agente de IA para Relacionamento Comunitário v1.0*:
assistente de escuta para o **agente de campo**, com registro íntegro, protocolo rastreável, triagem
**assistida** com revisão humana obrigatória, consulta de status, base de conhecimento aprovada,
trilha de auditoria completa e desligamento seguro (kill switch).

> O agente **não decide**: não determina direitos, culpa ou causalidade, não negocia, não encerra
> manifestações críticas e não publica respostas automaticamente. Esses limites estão em **código
> determinístico** (`backend/escuta/safety/`), não só no prompt.

## Arquitetura em uma tela

```
PWA agente de campo (frontend/)  ── offline: fila cifrada (AES-GCM) no IndexedDB, sync idempotente
        │  REST (X-Chave-Acesso → papel/território; em produção: SSO)
        ▼
FastAPI (backend/escuta/api)
  ├─ conversation.py   máquina de estados D-01…D-13 (o fluxo é código, não geração livre)
  ├─ safety/           emergência · sensíveis/retaliação · guarda de saída · mascaramento  ← antes e depois do LLM
  ├─ triage.py         regras + sugestão do modelo, política "o mais protetor vence"
  ├─ llm/              Claude (saída estruturada) | determinístico (sem LLM)  ← plugável
  ├─ knowledge.py      só conteúdo aprovado, com fonte e data; sem conteúdo → "não tenho a informação"
  ├─ services.py       UC-01…UC-12, fila humana, revisão, encaminhamento, anexos cifrados
  ├─ audit.py          append-only com cadeia de hash (adulteração detectável)
  └─ indicators.py     agregados com supressão de células < N, sem ranking de pessoas
SQLite (dev/piloto) → Postgres via ESCUTA_DATABASE_URL
```

## Rodar

```bash
cd backend
pip install -e ".[dev]"
python -m pytest              # 86 testes: critérios de aceite 1–19, diálogos D-01…D-13, adversariais
uvicorn escuta.api.app:app --port 8000
# abrir http://localhost:8000/app/  — chaves de dev: campo-dev, revisor-dev, sigilo-dev, gestor-dev, governanca-dev
```

Variáveis principais:

| Variável | Padrão | Observação |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Sem ela, o agente roda em **modo determinístico** (fluxo completo, resumo = fala original, triagem por regras). |
| `ESCUTA_LLM` | `auto` | `auto` \| `claude` \| `deterministico` |
| `ESCUTA_LLM_MODELO` | `claude-opus-5-5` | Esforço `low` por padrão (`ESCUTA_LLM_ESFORCO`). |
| `ESCUTA_DATABASE_URL` | `sqlite:///backend/escuta.db` | Postgres: `postgresql+psycopg://…` |
| `ESCUTA_CHAVE_CIFRA` | chave local de dev | **Obrigatória em produção** (KMS). Cifra contatos, anexos e turnos de conversa. |
| `ESCUTA_CHAVES_ACESSO` | chaves de dev | JSON `{chave: {papel, id, territorio}}`. Substituir por SSO. |
| `ESCUTA_MINIMO_N` | `5` | Mínimo por célula nos indicadores. |

Rotinas periódicas (agendar via cron): `POST /admin/rotinas` — sinaliza atrasos à coordenação e processa o
outbox de integrações (retry + dead-letter).

## Documentação

- [`docs/criterios_aceite.md`](docs/criterios_aceite.md) — matriz critério → teste → evidência, e o que fica para campo.
- [`docs/decisoes_e_lacunas.md`](docs/decisoes_e_lacunas.md) — decisões de desenho, limitações conhecidas e perguntas pendentes (cap. 17) que bloqueiam o piloto.
- `backend/escuta/prompts/system_prompt_v1.md` — prompt do cap. 7 (ativo governado; mudança exige comitê + reteste).
