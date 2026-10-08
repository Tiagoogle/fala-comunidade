# Prompt Mestre — Dashboard de Relacionamento com Comunidades (Mineração)

> **Como usar:** preencha as variáveis do bloco `0`, copie tudo a partir de `## PROMPT` e cole no
> modelo/ferramenta de geração (Claude, v0, Lovable, Bolt, Cursor etc.).
> **Execução em duas fases:** a Fase 1 (seções 1–10) gera a Visão Geral em alta fidelidade.
> Os módulos do Anexo A (Fase 2) devem ser pedidos **um por vez**, na mesma conversa ou projeto,
> depois que a Fase 1 estiver aprovada. Pedir 14 telas "com código completo" de uma só vez faz as
> ferramentas de geração truncarem o código ou entregarem telas rasas.
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
| `{{NOME_PRODUTO}}` | Fala Comunidade | Nome textual da solução |

---

## PROMPT

### 1. Papel

Você é um **time sênior de produto** composto por: (a) designer de produto especializado em
dashboards geoespaciais e data-viz acessível; (b) engenheiro front-end sênior; (c) especialista em
Relacionamento com Comunidades e Direitos Humanos em mineração, com domínio de IFC Performance
Standards (PS1, PS4, PS5, PS7), ICMM Mining Principles, Princípios Orientadores da ONU sobre
Empresas e Direitos Humanos (UNGPs), Convenção 169 da OIT e LGPD (Lei 13.709/2018);
(d) especialista em governança de dados e privacidade; (e) analista de operações minerárias e
riscos socioambientais. Cada decisão de interface deve passar pelo crivo dos cinco.

As referências normativas orientam a arquitetura e a governança do produto. Elas **não** são
parecer jurídico, certificação ou declaração de conformidade, e a interface nunca deve sugerir isso.

### 2. Objetivo

Construir o protótipo funcional de alta fidelidade de um **dashboard de monitoramento do
relacionamento entre a {{UNIDADE}} ({{EMPRESA}}) e as comunidades da sua área de influência**
em {{MUNICIPIOS_UF}}, usando a stack `{{STACK}}` e dados mock realistas.

O dashboard deve responder, em menos de 10 segundos de leitura, a quatro perguntas de um gestor:
1. **Onde** o relacionamento está se deteriorando?
2. **Por quê** (quais temas/demandas puxam a deterioração)?
3. **O que a empresa deve** (compromissos vencidos, manifestações sem resposta)?
4. **O que vem pela frente** nos próximos 7 dias (eventos operacionais e de diálogo com impacto
   comunitário potencial)?
5. **Que valor está sendo entregue** (projetos e investimentos sociais em dia, atrasados ou concluídos)?

O sistema apoia decisões humanas, escuta, prevenção e prestação de contas. Ele não substitui
mediação, consulta, participação comunitária nem julgamento profissional.

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
   elas mostra a nota "dados sob governança compartilhada (princípios CARE)". O sistema **nunca
   infere** essa identidade. O critério é a autoidentificação da própria comunidade (OIT 169,
   art. 1º, item 2), registrada por uma pessoa responsável, com a fonte indicada (ex.: certidão da
   Fundação Cultural Palmares, quando houver). A falta de certidão não pode servir de motivo para
   ocultar o selo de uma comunidade que se autoidentifica.
5. **Transparência de cálculo.** Todo índice composto tem um ícone "ⓘ Como calculamos" com
   fórmula, pesos, fonte, data da última atualização e limitações conhecidas.
6. **Ausência de dado ≠ zero.** Dado ausente é exibido com hachura e rótulo "sem dado"; dado com
   mais de 30 dias recebe badge "desatualizado".
7. **Interpretação contraintuitiva explícita.** Aumento de manifestações pode indicar **mais
   confiança no canal**, não piora da relação. Sempre exibir manifestações ao lado de taxa de
   resposta no prazo e percepção — nunca isoladas.
8. **Humano no circuito.** Nenhum alerta preditivo dispara ação automática; todo alerta exibe
   "sugestão para avaliação da equipe de RC".
9. **Natureza da informação visível.** Cada registro traz uma tag que diferencia: *relato
   comunitário*, *dado verificado*, *análise técnica*, *ação planejada* e *resposta institucional*.
   Medição ambiental não equivale a conclusão sobre responsabilidade ou dano.
10. **Natureza do compromisso visível.** Investimento social voluntário nunca aparece misturado com
    reparação, compensação, condicionante de licença ou TAC. Cada item mostra seu tipo, porque
    misturar esses tipos infla o "valor entregue" e é exatamente o que órgãos de controle e
    comunidades contestam.
11. **Risco atribuído à situação, não à comunidade.** Riscos são cadastrados por situação ou tema
    (ex.: "poeira no acesso da MG-030 no período seco") e só depois associados a um território.
    É proibido classificar uma comunidade ou um grupo como "de risco alto".
12. **Dados demonstrativos sinalizados.** Sem backend, um banner fixo exibe: "Dados
    demonstrativos — substituir por dados oficiais antes do uso operacional".
13. **Camadas sensíveis protegidas.** Ativos operacionais e partes interessadas respeitam perfil
    de acesso, deixam trilha de auditoria e não podem ser exportados por perfis sem autorização.

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
7. Projetos e Investimentos Sociais
8. Operações e Eventos
9. Monitoramento Socioambiental (água, ar/poeira, ruído, vibração)
10. Riscos e Mediação
11. Partes Interessadas *(cadeado — acesso restrito por perfil)*
12. Relatórios (ICMM, IFC, GRI 413 / GRI 14)
13. Configurações
- Na Fase 1, os itens 2 a 13 levam a rotas placeholder com o estado "Módulo em construção —
  ver Anexo A". Nada de telas falsas ou vazias que pareçam prontas.
- Rodapé da sidebar: ícone de folha + "Licença social se constrói todos os dias."

#### 4.3 Header de contexto (equivalente a "Fazenda / Safra / Área / Status")
- Título: **{{UNIDADE}}** · subtítulo com pin: {{MUNICIPIOS_UF}}
- Chip 1 — **{{CICLO}}** · "Fase: Operação"
- Chip 2 — **Área de influência:** 6 comunidades · ~18.400 pessoas (fonte: IBGE Censo 2022, setores censitários).
  População sempre como estimativa agregada, nunca como número exato.
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
  5. **Projetos sociais** — pontos ou polígonos com estágio e comunidades alcançadas, com tipo
     (voluntário / condicionante / reparação) diferenciado por forma, e não só por cor
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
  - projetos sociais relacionados e situações de atenção/mediação em andamento;
  - indicador de qualidade e frescor dos dados;
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
  (todas as componentes normalizadas 0–100; mostrar amostra e % de dados ausentes). O IR não é
  apresentado como "aprovação" da operação nem como julgamento da comunidade. Inspirado no modelo de níveis de licença social de
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
- Valor principal: **11 eventos** · "3 exigem comunicação preventiva".
- Gráfico de barras diário (Hoje, Sáb, Dom, Seg, Ter, Qua, Qui) com barras empilhadas:
  eventos de diálogo (reuniões, visitas, audiências, consultas) vs. eventos operacionais
  (detonações, manutenção de barragem, obras/alteração de acesso, transporte excepcional,
  monitoramentos programados).
- Vocabulário obrigatório: "evento com impacto comunitário potencial", "requer comunicação
  preventiva", "preparação de diálogo recomendada". Nunca rotular um evento como "conflito".
- Cada evento operacional mostra se o aviso prévio foi feito e qual é a evidência (canal, data).
- Chip climático contextual: "Período seco · risco de poeira ↑" (dado de previsão do INMET);
  justificativa: poeira é o principal vetor de manifestação no período seco.
- Lista curta de alertas: "Ter · Detonação programada a 1,2 km de Vila Esperança — comunicar
  com 48 h de antecedência".

#### 4.8 Faixa inferior — Registros de campo | Projetos sociais (equivalente a "Imagens de Drone")
- Duas abas na mesma faixa, mantendo o layout de referência: **Registros de campo** (padrão) e
  **Projetos sociais**.
- Aba Registros: 5 cards horizontais com miniatura, título e metadados:
  `RC_20260312_reuniao_vila-esperanca` · tipo (Reunião pública / Visita domiciliar / Vistoria de
  dano / Audiência) · data · participantes **em faixa** (ex.: "20–30", nunca o número exato) ·
  status do encaminhamento.
- Aba Projetos: 5 cards com nome, tipo (voluntário / condicionante / reparação), % executado
  físico vs. financeiro, comunidades alcançadas e próxima entrega; badge "sem evidência" quando
  não houver comprovação anexada.
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
| `--neutral` | `#6E8279` | sem dado / estado neutro |

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
11 eventos nos próximos 7 dias, 5 registros de campo, 3 ativos operacionais (cava, planta,
barragem), 12 compromissos (concluídos, em andamento, vencidos e um sem evidência) e 6 projetos
sociais (pelo menos um de cada tipo: voluntário, condicionante, reparação).

### 7. Estados e comportamento

- **Loading:** skeletons com a forma final dos cards (sem spinners genéricos).
- **Vazio:** mensagem orientada à ação ("Nenhuma manifestação aberta. Registre a próxima
  visita de campo.").
- **Erro de fonte:** card mantém último valor válido + badge "fonte indisponível desde hh:mm".
- **Filtros globais** (no header): período, comunidade, tema. Todos os componentes reagem.
- **Perfis de acesso** (simular com seletor no avatar): Analista RC (tudo), Gestor (tudo menos
  Partes Interessadas detalhado), Diretoria (somente agregados), Auditoria externa (somente
  leitura + trilha de cálculo), Operação (eventos e ativos necessários à execução), Governança
  de dados (fontes, qualidade, frescor e permissões). Conteúdo restrito aparece como
  "acesso restrito", sem revelar o que está protegido.
- **Exportação:** botão "Exportar relatório" gera PDF/CSV. Antes de gerar, um diálogo mostra
  escopo, período, filtros, solicitante, nível de confidencialidade, fontes, nota metodológica e
  dados suprimidos. A exportação é bloqueada quando inclui camadas que o perfil não pode ver.

### 7.1 IA (opcional, somente como apoio revisável)

Se houver IA, ela serve apenas para: classificar temas de manifestação, resumir históricos,
preparar briefings e rascunhos de resposta e apontar mudanças de tendência. Ela **não** envia
respostas, **não** decide se um relato é verdadeiro ou falso, **não** infere intenção e **não**
classifica pessoas ou comunidades. Toda saída exibe "Sugestão gerada por IA", a fonte, a data, uma
explicação curta, o botão "Revisar" e quem aprovou.

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
- [ ] Projetos voluntários, condicionantes e de reparação aparecem com o tipo explícito e nunca
      somados num único "investimento".
- [ ] Nenhum evento ou comunidade aparece rotulado como "conflito" ou "risco alto".
- [ ] Banner de dados demonstrativos visível; perfis Operação e Governança de dados alteram o
      conteúdo exibido; exportação bloqueia camadas não autorizadas.
- [ ] Rotas da Fase 2 exibem placeholder honesto, sem telas falsas.

### 10. Formato de entrega

1. Árvore de arquivos.
2. Código completo de cada arquivo (sem omissões "…").
3. `README.md` com: como rodar, como substituir o mock por fontes reais, dicionário de
   indicadores (nome, fórmula, fonte, periodicidade, responsável) e lista de premissas assumidas.
4. Ao final, liste **3 riscos éticos ou de interpretação** que o dashboard ainda não mitiga e
   sugira como tratá-los.

---

## Anexo A — Módulos da Fase 2 (pedir um por vez)

> Use o modelo: *"Com base no protótipo aprovado e mantendo todos os princípios da seção 3,
> implemente o módulo **X** conforme a especificação abaixo. Reutilize os componentes e tipos
> existentes."*

| Módulo | Núcleo da especificação |
|---|---|
| **Manifestações e Canal de Escuta** | Ciclo: recebida → triagem → análise → aguardando informação → encaminhada → em diálogo → resposta preparada → respondida → resolvida → encerrada → reaberta. Visões: tabela, kanban, timeline. Campos: território, canal, tema, relato, impacto percebido, operação relacionada, responsável, prazo, resposta, evidências, avaliação posterior. Temas adicionais: fornecedores locais, saúde e segurança, patrimônio cultural, uso do solo, direitos humanos, informação e transparência, conduta de terceiros. |
| **Compromissos** | Origem (reunião, condicionante, TAC, acordo), prazo, responsável, % execução, evidências, dependências, histórico. Status: planejado, em andamento, em validação, concluído, atrasado, suspenso, cancelado com justificativa, reaberto. Alertas: prazo próximo, vencido, sem atualização, evidência pendente. |
| **Projetos e Investimentos Sociais** | Tipo obrigatório (voluntário / condicionante / reparação / compensação), orçamento previsto vs. executado, execução física vs. financeira, público agregado alcançado, indicadores de **resultado** (não só de entrega), parceiro, próxima entrega, matriz de cobertura por comunidade. |
| **Operações e Eventos** | Ativos autorizados por perfil, obras, paradas, detonações, alterações de acesso, rotas, comunidades potencialmente afetadas, antecedência exigida vs. realizada, canal e evidência do aviso, registro pós-evento. |
| **Monitoramento Socioambiental** | Parâmetro, valor, unidade, limite aplicável **com a norma citada**, fonte, qualidade do dado, observação técnica. Medição, interpretação técnica e percepção comunitária aparecem em colunas separadas. |
| **Riscos e Mediação** | Matriz probabilidade × impacto **por situação/tema**, com sinais observados, fonte, medidas preventivas, responsável e próxima revisão. Mediação: temas centrais, convergências, divergências, encontros, compromissos relacionados, necessidade de escalonamento. |
| **Engajamento** | Reuniões, visitas, consultas, oficinas; participação agregada; temas sem devolutiva; cobertura territorial. Participação nunca vira ranking de comunidades: é lida junto com acessibilidade e representatividade. |

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
