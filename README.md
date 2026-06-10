# Fala Comunidade 🟢 — IA e Relacionamento com Comunidades na Mineração

**Fala Comunidade** é a evolução do nosso trabalho sobre Inteligência Artificial aplicada ao relacionamento com comunidades na mineração. O repositório agora tem duas frentes:

| Frente | O que é | Onde |
|---|---|---|
| **Canal da Comunidade** | Página pública com o assistente virtual e os canais oficiais (0800, ouvidoria) | [`index.html`](index.html) |
| **Central do Analista** 📱 | **Aplicativo mobile (PWA) que automatiza as tarefas manuais do analista de relacionamento com comunidades** | [`app/`](app/) |

---

## A Central do Analista

> *Do caderno de campo ao cockpit estratégico.*

O analista de relacionamento com comunidades passa o dia em campo — e, hoje, boa parte do seu tempo é consumida por tarefas manuais: anotar atendimentos no caderno e redigitar em planilhas, classificar manifestações, calcular prazos de cabeça, redigir respostas e comunicados, montar relatórios para a gerência e lembrar de cada promessa feita à comunidade. Cada hora gasta nisso é uma hora a menos de presença no território — justamente o que sustenta a **licença social para operar**.

A Central do Analista ataca exatamente essas tarefas:

| Tarefa manual de hoje | Como o app automatiza |
|---|---|
| Anotar no caderno e redigitar no escritório | **Registro em ~30 segundos**, por texto ou **ditado por voz**, com protocolo automático (`FC-AAAA-NNNN`), geolocalização e funcionamento **offline** |
| Classificar a manifestação e decidir a área responsável | **FalaIA classifica** em tempo real: categoria (poeira, vibração, água, fundiário, barragens/ZAS…), área responsável, tipo e sentimento |
| Definir prioridade e prazo "no feeling" | **Criticidade 1–5 calculada** (sentimento + urgência + termos de escalada como *bloqueio*, *Ministério Público*, *imprensa*) e **SLA automático** de resposta e solução |
| Controlar prazos em planilha | **Esteira de demandas** com contagem regressiva, alertas de SLA estourando e linha do tempo de tratativas |
| Redigir resposta para cada caso | **Resposta sugerida** pronta por categoria, com protocolo e prazo, para copiar ou enviar direto no WhatsApp |
| Redigir comunicados (detonação, interrupção de via, reunião…) | **Gerador de comunicados** com data, hora e comunidade preenchidas |
| Montar o relatório semanal/mensal | **Relatório em 1 toque**: resumo executivo em prosa, números, temas em alta, risco por território e **recomendações de ação** |
| Perceber que uma comunidade vai "esquentar" | **Índice de risco social (0–100) por comunidade**, combinando criticidade, SLA, tendência, sentimento e menções a escalada |
| Lembrar das promessas feitas em reunião | **Gestão de compromissos e condicionantes** com prazos e alertas |
| Manter o mapa de relacionamentos | **Stakeholders com matriz influência × interesse**, histórico automático de interações e alerta de “relacionamento esfriando” (30+ dias sem contato) |

### Por que é estratégico (e não só operacional)

1. **Licença social para operar** — o índice de risco social transforma registros dispersos em sinal antecipado de conflito (bloqueios, judicialização, imprensa), permitindo agir **antes** da crise.
2. **Memória institucional** — cada interação vira dado estruturado e exportável (CSV/JSON), em vez de morrer no caderno de um analista.
3. **Compliance e ESG** — SLAs, condicionantes e evidências de atendimento ficam rastreáveis, prontos para auditorias e relatórios de desempenho social.
4. **Gestão por dados** — a liderança passa a enxergar temas em alta, territórios críticos e cumprimento de prazos em tempo real.

### A FalaIA — duas camadas de inteligência

- **IA embarcada (offline-first)** — classificação por taxonomia do setor mineral, análise de sentimento em PT-BR, cálculo de criticidade/SLA, índice de risco, geração de respostas, comunicados e relatórios. Roda 100% no dispositivo: **funciona sem sinal**, realidade de quem trabalha em território.
- **IA conectada (opcional)** — o chat da FalaIA pode ser ligado à **API do Claude** (`claude-opus-4-8` por padrão) para perguntas livres, recebendo um contexto compacto dos indicadores locais. Configurável em *Ajustes*. ⚠️ No piloto a chave fica no dispositivo; em produção, usar um proxy corporativo (a chave nunca deve ir ao cliente).

---

## Como usar

### Direto no navegador (GitHub Pages ou Cloudflare Workers)

Publique o repositório no GitHub Pages e acesse `https://<usuario>.github.io/fala-comunidade/app/` no celular — ou use o deploy automático no **Cloudflare Workers** ([`wrangler.jsonc`](wrangler.jsonc) já configura o site como assets estáticos; o Workers Builds publica a cada push). No Android (Chrome): **Adicionar à tela inicial**. No iPhone (Safari): **Compartilhar → Adicionar à Tela de Início**. O app instala como PWA e funciona offline.

### Localmente

```bash
python3 -m http.server 8080
# abra http://localhost:8080/app/
```

O primeiro acesso carrega **dados fictícios de demonstração** (comunidades, stakeholders, demandas com SLAs em diferentes estados) para o app já nascer vivo. Em *Ajustes* é possível apagá-los e começar do zero.

### Testes

```bash
node tools/test-ia.mjs      # motor de IA (classificação, sentimento, risco, textos)
node tools/test-stats.mjs   # integração: seed + indicadores + relatório
node tools/test-views.mjs   # smoke: todas as telas renderizam
node tools/gen-icons.mjs    # regenera os ícones PNG do PWA
```

---

## Arquitetura

```
index.html, style.css          → página pública (canal da comunidade)
app/
  index.html                   → shell do PWA (Central do Analista)
  manifest.webmanifest, sw.js  → instalação + offline (cache do shell)
  css/app.css                  → UI mobile-first (identidade Vale)
  js/util.js                   → utilidades (datas, clipboard, share)
  js/ia.js                     → FalaIA: motor de IA embarcado (puro, testável)
  js/db.js                     → dados locais (localStorage) + seed de demonstração
  js/stats.js                  → indicadores: SLA, risco, temas, relatório
  js/views.js                  → telas (funções puras → HTML)
  js/app.js                    → roteador, eventos, voz, GPS, conector Claude
tools/                         → testes em Node + gerador de ícones
```

Decisões de projeto:

- **Vanilla JS, sem build** — qualquer estático serve (GitHub Pages, intranet); zero dependências para auditar.
- **Offline-first** — service worker + dados locais; o campo não tem sinal, o app não pode depender dele.
- **IA embarcada com regras auditáveis** — taxonomia e pesos explícitos no código (importante em tema sensível como relação com comunidades), com camada LLM opcional por cima.
- **Funções puras testáveis em Node** — motor de IA, indicadores e telas têm suíte de testes sem navegador.

## Privacidade (LGPD)

Os dados ficam **somente no dispositivo do analista** (localStorage). Não há backend nem telemetria. Exportações (CSV/JSON/compartilhar) são ações explícitas do usuário. Registrar apenas dados pessoais necessários ao atendimento, com conhecimento do titular, conforme a política da empresa.

## Roadmap

- [ ] Sincronização multi-analista (backend corporativo + SSO)
- [ ] Proxy seguro para a API do Claude (chave fora do cliente) e transcrição de atas de reunião
- [ ] Fotos anexas com compressão (IndexedDB) e mapa de calor das ocorrências georreferenciadas
- [ ] Integração com BI corporativo (Power BI) e com o canal 0800/ouvidoria
- [ ] Notificações push de SLA e modo multi-território para coordenadores

---

*Projeto-piloto. "Vale" é usado como contexto de estudo; comunidades, pessoas e dados de demonstração são fictícios.*
