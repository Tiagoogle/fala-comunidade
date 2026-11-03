# Deploy: Fly.io (São Paulo) + Netlify

```
navegador ──HTTPS──► Netlify (alocomunidade)  ── /api/* proxy assinado ──► Fly.io gru (escuta-mais)
                     frontend/ (PWA estática)                                FastAPI + SQLite em volume /data
```

Os dados (banco, anexos cifrados) ficam **no volume do Fly em São Paulo**. A Netlify só serve arquivos
estáticos e repassa `/api/*`. Ela não guarda nenhum dado de manifestação: o service worker cacheia só o
shell do app.

## 1. Backend no Fly (uma vez)

```bash
fly auth login
fly apps create escuta-mais
fly volumes create escuta_dados --region gru --size 3      # GB; uma única máquina (SQLite)

# Segredos: nunca em arquivo versionado
fly secrets set -a escuta-mais \
  ESCUTA_CHAVE_CIFRA="$(python3 -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')" \
  ESCUTA_SEGREDO_PROXY="$(openssl rand -hex 32)" \
  ESCUTA_CHAVES_ACESSO='{"<chave-longa-aleatoria>":{"papel":"agente_campo","id":"campo-01","territorio":"MG"}, "...": {}}'
# Opcional, só depois do parecer de governança sobre o provedor de IA:
# fly secrets set -a escuta-mais ANTHROPIC_API_KEY=...

fly deploy            # na raiz do repositório (usa fly.toml + backend/Dockerfile)
curl https://escuta-mais.fly.dev/saude
```

**Guarde `ESCUTA_CHAVE_CIFRA` no cofre da empresa.** Sem ela, contatos, anexos e turnos de conversa
cifrados ficam ilegíveis para sempre.

A aplicação **se recusa a subir** em produção (`ESCUTA_AMBIENTE=producao`) se faltar a chave de cifra,
se as chaves de acesso não forem explícitas ou contiverem `*-dev`, ou se o proxy for confiável sem
segredo.

Gere as chaves de acesso com `openssl rand -hex 24`, uma por pessoa e papel. Papéis:
- `agente_campo`
- `revisor`
- `revisor_sigiloso`: lista nominal da Ouvidoria, pergunta O3
- `gestor`
- `governanca`

Isso é provisório: o piloto deve migrar para SSO.

## 2. Deploy automático (GitHub Actions)

- `ci.yml` roda em todo PR e em `main`: testes, migrações em dia com os modelos e build da imagem.
- `deploy.yml` roda após o CI verde em `main` e executa `flyctl deploy --remote-only`.

Configure no GitHub (Settings → Secrets and variables → Actions):
- `FLY_API_TOKEN` = saída de `fly tokens create deploy -a escuta-mais`;
- crie o environment `producao` (Settings → Environments) para exigir aprovação manual de deploy, se quiser.

## 3. Frontend na Netlify

O `netlify.toml` já define `publish = "frontend"`, o proxy `/api/*` e os headers de segurança (CSP etc.).

No painel do site **alocomunidade** → Site configuration → Environment variables, crie
**`ESCUTA_SEGREDO_PROXY`** com **o mesmo valor** do secret do Fly. A Netlify assina cada requisição
repassada (JWT em `x-nf-sign`), e o backend só usa o IP do cliente para o limite de tentativas quando a
assinatura confere.

## 4. Cloudflare: desconectar

Os projetos Workers `fala-comunidade` e `falacomunidade` falham em 0 s desde o PR #5 por falta de
configuração. No painel do Cloudflare → Workers & Pages → cada projeto → Settings → Builds →
**Disconnect** (ou apague os projetos). Também pode apagar a branch `cloudflare/workers-autoconfig`.

## 5. Operação

| Tarefa | Como |
|---|---|
| Backup | `fly volumes snapshots list escuta_dados` (snapshots diários automáticos). Antes de migrações: `fly volumes snapshots create <id>`. |
| Logs | `fly logs -a escuta-mais` |
| Rotinas (atrasos, outbox) | Agendar `POST /admin/rotinas` com chave de governança (ex.: GitHub Actions `schedule` a cada 30 min). |
| Kill switch | Aba Governança do app, ou `POST /api/admin/chaves`. |
| Migração de schema | Nova revisão: `cd backend && alembic revision --autogenerate -m "..."`, revisar o arquivo e commitar. O container aplica no boot. |
| Escalar para Postgres | Criar Postgres (Fly Postgres em `gru` ou equivalente no Brasil), `pip install ".[postgres]"`, `fly secrets set ESCUTA_DATABASE_URL=postgresql+psycopg://...`, migrar dados e só então permitir mais de uma máquina. Anexos ainda exigem volume ou object storage. |
| Rotação da chave de cifra | **Ainda não automatizada.** Exige re-cifrar `pessoa`, `turno_conversa` e os anexos. Planejar antes do piloto. |

## Limites conhecidos deste desenho

- **Uma máquina só** (SQLite em volume). Se ela cair, o app fica indisponível até reiniciar. A PWA
  continua registrando offline e sincroniza depois, mas a fila P1 depende do plantão humano por telefone
  enquanto isso.
- O IP usado no limite de tentativas vem do `x-nf-client-connection-ip` assinado pela Netlify. Acesso
  direto ao `fly.dev` usa o `Fly-Client-IP`. Nenhum dos dois é identificação de pessoa: é só controle
  de abuso e não é guardado fora da trilha de tentativas negadas.
