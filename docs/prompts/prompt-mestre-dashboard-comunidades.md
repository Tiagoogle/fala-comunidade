# Prompt Mestre — Dashboard de Relacionamento com Comunidades (Mineração)

> **Como usar:** preencha as variáveis do bloco `0`, copie tudo a partir de `## PROMPT` e cole no
> modelo/ferramenta de geração (Claude, v0, Lovable, Bolt, Cursor etc.).
> A referência visual é um dashboard agrícola dark-mode (sidebar + mapa central com camadas +
> cards de KPI à direita + faixa de imagens na base). O prompt **mantém a gramática visual** e
> **substitui a semântica**: não monitoramos "talhões", monitoramos **a qualidade de uma relação**.

---

## 0. Variáveis (preencha antes de usar)

| Variável | Exemplo | Observação |
|---|---|---|
| `{{EMPRESA}}` | Mineradora Exemplo S.A. | Use nome fictício em protótipos públicos |
| `{{UNIDADE}}` | Complexo Serra do Cedro | Unidade operacional / complexo |
| `{{MUNICIPIOS_UF}}` | Itabirito e Ouro Preto – MG | Municípios da área de influência |
| `{{CICLO}}` | Ciclo 2025/2026 | Período de gestão ou fase de licenciamento |
| `{{STACK}}` | React + Vite + TypeScript + Tailwind + MapLibre GL + Recharts | Alternativa: HTML único + Leaflet + Chart.js |
| `{{IDIOMA}}` | pt-BR | |
| `{{USUARIO_LOGADO}}` | Analista de Relacionamento | Perfil, não nome real |

---

## PROMPT

### 1. Papel

Você é um **time sênior de produto** composto por: (a) designer de produto especializado em
dashboards geoespaciais e data-viz acessível; (b) engenheiro front-end sênior; (c) especialista em
Relacionamento com Comunidades e Direitos Humanos em mineração, com domínio de IFC Performance
Standards (PS1, PS4, PS5, PS7), ICMM Mining Principles, Princípios Orientadores da ONU sobre
Empresas e Direitos Humanos (UNGPs), Convenção 169 da OIT e LGPD (Lei 13.709/2018).
Cada decisão de interface deve passar pelo crivo dos três.

### 2. Objetivo

Construir o protótipo funcional de alta fidelidade de um **dashboard de monitoramento do
relacionamento entre a {{UNIDADE}} ({{EMPRESA}}) e as comunidades da sua área de influência**
em {{MUNICIPIOS_UF}}, usando a stack `{{STACK}}` e dados mock realistas.

O dashboard deve responder, em menos de 10 segundos de leitura, a quatro perguntas de um gestor:
1. **Onde** o relacionamento está se deteriorando?
2. **Por quê** (quais temas/demandas puxam a deterioração)?
3. **O que a empresa deve** (compromissos vencidos, manifestações sem resposta)?
4. **O que vem pela frente** nos próximos 7 dias (eventos operacionais e de diálogo com potencial de tensão)?

### 3. Princípios inegociáveis (aplique em todo o produto)

1. **Monitorar a relação, não vigiar pessoas.** Os indicadores medem principalmente o desempenho
   da empresa (prazos, respostas, compromissos cumpridos) e a percepção agregada da comunidade.
   É proibido perfilar indivíduos, exibir nomes de lideranças no mapa ou criar "score de risco"
   por pessoa.
2. **Linguagem não estigmatizante.** Nunca rotular comunidades como "hostis", "problemáticas" ou
   "piores". Use "requer atenção", "relação em fragilização", "prioridade de diálogo".
3. **LGPD por padrão.** Dados agregados por comunidade (mínimo de 5 registros por célula antes de
   exibir; abaixo disso mostrar "n < 5 — dado suprimido"). Dados sensíveis (art. 5º, II, e art. 11:
   origem étnica, religião, opinião política, saúde) nunca aparecem na visão geral. Fotos de campo
   só com flag de consentimento e rostos desfocados por padrão.
4. **Povos e comunidades tradicionais.** Comunidades indígenas, quilombolas ou tradicionais
   exibem selo "CLPI — Consulta Livre, Prévia e Informada (OIT 169)" e qualquer indicador sobre
   elas mostra a nota "dados sob governança compartilhada (princípios CARE)".
5. **Transparência de cálculo.** Todo índice composto tem um ícone "ⓘ Como calculamos" com
   fórmula, pesos, fonte, data da última atualização e limitações conhecidas.
6. **Ausência de dado ≠ zero.** Dado ausente é exibido com hachura e rótulo "sem dado"; dado com
   mais de 30 dias recebe badge "desatualizado".
7. **Interpretação contraintuitiva explícita.** Aumento de manifestações pode indicar **mais
   confiança no canal**, não piora da relação. Sempre exibir manifestações ao lado de taxa de
   resposta no prazo e percepção — nunca isoladas.
8. **Humano no circuito.** Nenhum alerta preditivo dispara ação automática; todo alerta exibe
   "sugestão para avaliação da equipe de RC".

### 4. Arquitetura de informação (espelhar o layout de referência)

Canvas desktop 1440×900, dark mode, grid de 12 colunas. Responsivo até 1280 px; abaixo de
1024 px os cards da direita descem para baixo do mapa.

```
┌───────────┬──────────────────────────────────────────────────────────┬──────────────────┐
│ SIDEBAR   │ HEADER DE CONTEXTO (unidade · ciclo · área de influência · status)          │
│           ├──────────────────────────────────────────────────────────┼──────────────────┤
│           │ MAPA TERRITORIAL COM CAMADAS (toggle) + legenda          │ CARD 1: Índice   │
│           │ + miniaturas de camada à direita do mapa                 │ de Relacionamento│
│           │                                                          ├──────────────────┤
│           │                                                          │ CARD 2: Manifes- │
│           │                                                          │ tações & SLA     │
│           ├──────────────────────────────────────────────────────────┼──────────────────┤
│ rodapé    │ FAIXA: Registros de campo (5 cards)                      │ CARD 3: Próximos │
│ missão    │                                                          │ 7 dias           │
└───────────┴──────────────────────────────────────────────────────────┴──────────────────┘
```

#### 4.1 Topbar
- Logo textual "Fala Comunidade" + tagline: "Diálogo contínuo. Território mais justo."
- À direita: sino de notificações (com contador), avatar com iniciais e perfil `{{USUARIO_LOGADO}}`.
- Indicador de frescor global: "Dados atualizados há 2 h · Fonte: Sistema de Manifestações".

#### 4.2 Sidebar (ícone + rótulo; item ativo com fundo de destaque)
1. Visão Geral *(ativo)*
2. Comunidades
3. Mapa Territorial
4. Manifestações (queixas, sugestões, elogios, pedidos de informação)
5. Compromissos (pactuados em reuniões, condicionantes, TACs)
6. Engajamento (reuniões, visitas, audiências)
7. Monitoramento Socioambiental (água, ar/poeira, ruído, vibração)
8. Partes Interessadas *(cadeado — acesso restrito por perfil)*
9. Relatórios (ICMM, IFC, GRI 413 / GRI 14)
10. Configurações
- Rodapé da sidebar: ícone de folha + "Licença social se constrói todos os dias."

#### 4.3 Header de contexto (equivalente a "Fazenda / Safra / Área / Status")
- Título: **{{UNIDADE}}** · subtítulo com pin: {{MUNICIPIOS_UF}}
- Chip 1 — **{{CICLO}}** · "Fase: Operação"
- Chip 2 — **Área de influência:** 6 comunidades · ~18.400 pessoas (fonte: IBGE Censo 2022, setores censitários)
- Chip 3 — **Status do relacionamento:** "Atenção" (ponto âmbar) — regra: Estável (IR ≥ 70), Atenção (50–69), Crítico (< 50)

#### 4.4 Mapa territorial (componente central)
- Base: imagem de satélite escurecida (opacidade 60 %) com polígonos das comunidades, contorno
  da cava/planta/barragem da {{UNIDADE}} em linha tracejada branca e acessos rodoviários.
- Cada polígono tem rótulo flutuante: nome da comunidade + valor da camada ativa
  (ex.: "Córrego das Pedras · IR 48").
- **Toggles de camada** (pills no topo esquerdo, uma ativa por vez):
  1. **Relacionamento (IR)** — coroplético por Índice de Relacionamento
  2. **Manifestações** — mapa de calor de densidade por tema (filtro de tema)
  3. **Riscos operacionais** — Zona de Autossalvamento (ZAS) de barragem (Lei 12.334/2010, alterada
     pela Lei 14.066/2020), raio de detonação, rotas de caminhões
  4. **Socioambiental** — pontos de monitoramento de água, poeira (PM10) e ruído com semáforo
     em relação ao limite legal
- Seletor de data (canto superior direito) + controles de zoom, centralizar e camadas.
- Miniaturas verticais à direita do mapa (como na referência): "Mapa IR", "Riscos", "Monitoramento".
- **Legenda** inferior esquerda: escala sequencial **acessível a daltônicos** (paleta tipo
  *cividis* ou *viridis*, NUNCA vermelho→verde), 0–100, com rótulos textuais
  "Crítico / Atenção / Estável" e padrão hachurado para "sem dado".
- **Clique em uma comunidade** abre painel lateral (drawer) com:
  - tipologia (urbana, rural, tradicional/quilombola, assentamento) e população estimada;
  - IR atual + tendência de 6 meses;
  - top 3 temas de manifestação;
  - compromissos: em dia / vencidos / cumpridos (barra empilhada);
  - último contato da equipe de RC e próximo evento agendado;
  - selo CLPI quando aplicável;
  - botão "Gerar briefing da comunidade" (exporta PDF de 1 página).

#### 4.5 Card 1 — Índice de Relacionamento (equivalente a "Produtividade")
- Valor principal grande: **62** /100 · delta "↓ 4 pts vs. trimestre anterior" (vermelho-âmbar,
  com seta e texto, não só cor).
- Sparkline de 12 meses.
- Linhas de detalhe:
  - Média da área de influência: 62
  - Relação mais sólida: Bairro São José (78)
  - Prioridade de diálogo: Córrego das Pedras (48)
- ⓘ **Como calculamos** (pesos configuráveis em Configurações):
  `IR = 0,30·Percepção + 0,30·Compromissos cumpridos no prazo + 0,20·Respostas no prazo + 0,20·Participação em espaços de diálogo`
  (todas as componentes normalizadas 0–100). Inspirado no modelo de níveis de licença social de
  Thomson & Boutilier e no modelo de confiança de Moffat & Zhang (2014).

#### 4.6 Card 2 — Manifestações & SLA (equivalente a "Umidade do solo")
- Valor principal: **87%** respondidas no prazo · delta "↑ 5 pts vs. mês anterior".
- Sparkline de volume semanal.
- Linhas de detalhe:
  - Abertas: 34 (9 vencidas)
  - Tempo médio de 1ª resposta: 4,2 dias (meta ≤ 5)
  - Tema dominante: Poeira (38%) · Água (21%) · Tráfego (17%)
- Nota de rodapé: "Mais manifestações podem indicar mais confiança no canal — leia junto com IR."
- Referência: critérios de eficácia de mecanismos de queixa (UNGP, Princípio 31).

#### 4.7 Card 3 — Próximos 7 dias (equivalente a "Previsão de chuva")
- Valor principal: **11 eventos** · "3 com potencial de tensão".
- Gráfico de barras diário (Hoje, Sáb, Dom, Seg, Ter, Qua, Qui) com barras empilhadas:
  eventos de diálogo (reuniões, visitas) vs. eventos operacionais (detonações, manutenção de
  barragem, obras em acesso).
- Chip climático contextual: "Período seco · risco de poeira ↑" (dado de previsão do INMET);
  justificativa: poeira é o principal vetor de manifestação no período seco.
- Lista curta de alertas: "Ter · Detonação programada a 1,2 km de Vila Esperança — comunicar
  com 48 h de antecedência".

#### 4.8 Faixa inferior — Registros de campo (equivalente a "Imagens de Drone")
- 5 cards horizontais com miniatura, título e metadados:
  `RC_20260312_reuniao_vila-esperanca` · tipo (Reunião pública / Visita domiciliar / Vistoria de
  dano / Audiência) · data · nº participantes · status do encaminhamento.
- Rostos desfocados por padrão; badge "Consentimento ✓" ou "Sem consentimento — imagem oculta".
- Ação "Ver todos" no canto superior direito.

### 5. Design system

| Token | Valor | Uso |
|---|---|---|
| `--bg` | `#0B1210` | fundo da página |
| `--surface` | `#111A17` | cards e sidebar |
| `--surface-2` | `#16231F` | hover, drawer |
| `--border` | `#1F2E29` | divisórias 1 px |
| `--text` | `#E6EFEA` | texto principal |
| `--text-muted` | `#8FA39A` | rótulos secundários |
| `--accent` | `#2BD46B` | item ativo, positivos, CTA |
| `--warning` | `#F2B233` | atenção |
| `--critical` | `#E5484D` | crítico (sempre com ícone + texto) |
| `--info` | `#4CC3D9` | eventos de diálogo |

- Tipografia: **Inter** (UI) e **JetBrains Mono** (IDs de registro). Números de KPI em 40 px / 600,
  rótulos 12 px / 500 em caixa normal.
- Raio 12 px nos cards, 8 px nos chips; sombras mínimas; espaçamento base 8 px.
- Contraste mínimo **WCAG 2.2 AA** (4,5:1 texto, 3:1 elementos gráficos). Nenhuma informação
  transmitida apenas por cor.
- Ícones: Lucide (linha 1,5 px).
- Micro-interações: hover nos polígonos realça contorno (2 px `--accent`) e mostra tooltip;
  transições ≤ 200 ms; respeitar `prefers-reduced-motion`.

### 6. Dados mock (crie arquivo `src/data/mock.ts` ou `<script type="application/json">`)

Use **somente nomes fictícios**. Inclua, no mínimo:

```ts
type Tipologia = "urbana" | "rural" | "tradicional_quilombola" | "assentamento";

interface Comunidade {
  id: string;
  nome: string;                // fictício
  tipologia: Tipologia;
  populacaoEstimada: number;   // agregada (IBGE Censo 2022, setor censitário)
  clpi: boolean;               // true para povos e comunidades tradicionais
  geometria: GeoJSON.Polygon;  // coordenadas plausíveis no entorno de {{MUNICIPIOS_UF}}
  ir: { atual: number; serie12m: number[]; componentes: {
        percepcao: number; compromissosNoPrazo: number;
        respostasNoPrazo: number; participacao: number; } };
  manifestacoes: { abertas: number; vencidas: number; porTema: Record<Tema, number> };
  compromissos: { emDia: number; vencidos: number; cumpridos: number };
  ultimoContato: string;       // ISO date
  atualizadoEm: string;        // ISO date — usar para badge "desatualizado"
}

type Tema = "poeira" | "agua" | "ruido_vibracao" | "trafego" | "emprego_renda"
          | "barragem_seguranca" | "reassentamento" | "outros";
```

Comunidades sugeridas (6): **Vila Esperança** (urbana), **Córrego das Pedras** (rural, IR 48),
**Quilombo Boa Vista** (tradicional_quilombola, `clpi: true`, um campo propositalmente sem dado),
**Assentamento Nova Aurora** (assentamento), **Bairro São José** (urbana, IR 78),
**Sítio Lajeado** (rural, `atualizadoEm` com mais de 30 dias para testar o badge).
Gere também: 12 meses de série histórica, 34 manifestações abertas distribuídas por tema,
11 eventos nos próximos 7 dias e 5 registros de campo.

### 7. Estados e comportamento

- **Loading:** skeletons com a forma final dos cards (sem spinners genéricos).
- **Vazio:** mensagem orientada à ação ("Nenhuma manifestação aberta. Registre a próxima
  visita de campo.").
- **Erro de fonte:** card mantém último valor válido + badge "fonte indisponível desde hh:mm".
- **Filtros globais** (no header): período, comunidade, tema. Todos os componentes reagem.
- **Perfis de acesso** (simular com seletor no avatar): Analista RC (tudo), Gestor (tudo menos
  Partes Interessadas detalhado), Diretoria (somente agregados), Auditoria externa (somente
  leitura + trilha de cálculo).
- **Exportação:** botão "Exportar relatório" gera PDF/CSV com nota metodológica.

### 8. Requisitos técnicos

- Stack: `{{STACK}}`. Componentização clara (`Sidebar`, `ContextHeader`, `TerritoryMap`,
  `LayerToggle`, `KpiCard`, `CommunityDrawer`, `FieldRecordsStrip`, `MethodTooltip`).
- Mapa: GeoJSON local; tiles gratuitos (ex.: Esri World Imagery ou OpenStreetMap) com atribuição.
- Sem chamadas a APIs pagas; sem chaves embutidas no código.
- Acessibilidade: navegação completa por teclado, `aria-label` em todos os controles, foco
  visível, gráficos com tabela alternativa (`<details>` "ver dados").
- Código tipado, sem `any`; dados isolados da UI para trocar mock por API real.

### 9. Critérios de aceite (verifique antes de entregar)

- [ ] O layout espelha a referência: sidebar, header de contexto com 3 chips, mapa com 4 camadas
      e legenda, 3 cards de KPI à direita, faixa de 5 registros na base.
- [ ] Nenhuma escala vermelho→verde; legenda legível por daltônicos.
- [ ] Todo índice tem "ⓘ Como calculamos" com fórmula e data.
- [ ] Quilombo Boa Vista exibe selo CLPI e o campo sem dado aparece hachurado, não como zero.
- [ ] Sítio Lajeado exibe badge "desatualizado".
- [ ] Nenhum nome de pessoa física aparece na Visão Geral; células com n < 5 suprimidas.
- [ ] Linguagem não estigmatizante em todos os rótulos.
- [ ] Contraste AA verificado; navegação por teclado funcional.
- [ ] Clique em comunidade abre drawer com todos os itens do item 4.4.

### 10. Formato de entrega

1. Árvore de arquivos.
2. Código completo de cada arquivo (sem omissões "…").
3. `README.md` com: como rodar, como substituir o mock por fontes reais, dicionário de
   indicadores (nome, fórmula, fonte, periodicidade, responsável) e lista de premissas assumidas.
4. Ao final, liste **3 riscos éticos ou de interpretação** que o dashboard ainda não mitiga e
   sugira como tratá-los.

---

## Referências para fundamentar o produto

- IFC — Performance Standards on Environmental and Social Sustainability (2012):
  https://www.ifc.org/en/insights-reports/2012/ifc-performance-standards
- ICMM — Mining Principles: https://www.icmm.com/en-gb/our-principles/mining-principles
- ONU — Guiding Principles on Business and Human Rights (2011), Princípio 31:
  https://www.ohchr.org/sites/default/files/documents/publications/guidingprinciplesbusinesshr_en.pdf
- Convenção 169 da OIT — consolidada no Brasil pelo Decreto 10.088/2019:
  https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2019/decreto/d10088.htm
- LGPD — Lei 13.709/2018: https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm
- Política Nacional de Segurança de Barragens — Lei 12.334/2010 (alterada pela Lei 14.066/2020):
  https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2010/lei/l12334.htm
- GIDA — CARE Principles for Indigenous Data Governance: https://www.gida-global.org/care
- GRI 413: Local Communities (2016) e GRI 14: Mining Sector (2024): https://www.globalreporting.org
- Moffat, K. & Zhang, A. (2014). *The paths to social licence to operate: An integrative model
  explaining community acceptance of mining.* Resources Policy, 39, 61–70.
- Franks, D. et al. (2014). *Conflict translates environmental and social risk into business
  costs.* PNAS, 111(21), 7576–7581.
- Thomson, I. & Boutilier, R. — modelo de níveis da licença social para operar
  (https://socialicense.com).
