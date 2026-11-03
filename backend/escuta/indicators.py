"""Indicadores agregados sem dados pessoais (spec UC-12, cap. 13).

- supressão de células pequenas (mínimo N por célula, configurável);
- rota sigilosa nunca aparece em recortes comuns — só como total agregado;
- sem ranking de pessoas ou equipes (§13.6);
- subnotificação: território sem manifestação recente é sinalizado como
  "possível subnotificação a verificar em campo", nunca como satisfação.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit
from .config import get_settings
from .models import AvaliacaoHumana, EventoStatus, ItemFilaHumana, Manifestacao, agora
from .services import AcessoNegado, Ator, _aware


def _suprimir(contagem: Counter, n: int) -> dict[str, int | str]:
    return {k: (v if v >= n else f"<{n}") for k, v in sorted(contagem.items())}


def painel(db: Session, ator: Ator, dias: int = 90, territorios_esperados: list[str] | None = None) -> dict:
    if ator.papel not in ("gestor", "governanca", "revisor", "revisor_sigiloso"):
        raise AcessoNegado("painel restrito a gestão, governança e revisores")
    n = get_settings().minimo_n_indicadores
    desde = agora() - timedelta(days=dias)
    todas = [m for m in db.execute(select(Manifestacao)).scalars() if _aware(m.criada_em) >= desde]
    comuns = [m for m in todas if m.rota == "comum"]
    sigilosas = len(todas) - len(comuns)

    # tempo até primeira ação humana (avaliação, assunção de fila ou status manual)
    tempos: list[float] = []
    fora_janela = 0
    criticos = 0
    revisados_devidos = [0, 0]
    s = get_settings()
    for m in todas:
        marcos = [a.avaliada_em for a in db.execute(select(AvaliacaoHumana).where(AvaliacaoHumana.id_manifestacao == m.id_manifestacao)).scalars()]
        marcos += [i.assumido_em for i in db.execute(select(ItemFilaHumana).where(ItemFilaHumana.id_manifestacao == m.id_manifestacao)).scalars() if i.assumido_em]
        marcos += [e.criado_em for e in db.execute(select(EventoStatus).where(EventoStatus.id_manifestacao == m.id_manifestacao)).scalars()
                   if not e.autor_mudanca.startswith("sistema")]
        primeiro = min((_aware(x) for x in marcos), default=None)
        if primeiro:
            tempos.append((primeiro - _aware(m.criada_em)).total_seconds() / 3600)
        prio = m.prioridade_validada or m.prioridade_sugerida
        if prio in ("P1", "P2"):
            criticos += 1
            limite = timedelta(hours=s.janelas[prio].horas_uteis_alvo)
            if primeiro is None and agora() - _aware(m.criada_em) > limite or primeiro and primeiro - _aware(m.criada_em) > limite:
                fora_janela += 1
        if m.revisao_obrigatoria:
            revisados_devidos[1] += 1
            if m.avaliacoes:
                revisados_devidos[0] += 1

    reclass = sum(1 for m in todas for a in m.avaliacoes if a.resultado == "reclassificada")
    avaliadas = sum(1 for m in todas if m.avaliacoes)
    contestacoes = sum(1 for m in todas for a in m.adendos if a.tipo == "contestacao")

    subnotificacao = []
    if territorios_esperados:
        com_registro = {m.territorio_uf for m in todas} | {m.localidade for m in todas if m.localidade}
        subnotificacao = [t for t in territorios_esperados if t not in com_registro]

    resultado = {
        "periodo_dias": dias,
        "minimo_n_por_celula": n,
        "total_manifestacoes": len(todas) if len(todas) >= n else f"<{n}",
        "sigilosas_total": sigilosas if sigilosas >= n or sigilosas == 0 else f"<{n}",
        "por_tema": _suprimir(Counter(m.tema_sugerido or "nao_classificado" for m in comuns), n),
        "por_tipo": _suprimir(Counter(m.tipo_sugerido or "nao_classificado" for m in comuns), n),
        "por_territorio": _suprimir(Counter(m.territorio_uf for m in comuns), n),
        "por_canal": _suprimir(Counter(m.canal_origem for m in comuns), n),
        "por_prioridade": _suprimir(Counter((m.prioridade_validada or m.prioridade_sugerida or "-") for m in comuns), n),
        "tempo_mediano_primeira_acao_humana_h": round(median(tempos), 1) if len(tempos) >= n else None,
        "casos_criticos_fora_da_janela": fora_janela if criticos >= n else f"<{n} casos críticos",
        "revisoes_humanas_realizadas": f"{revisados_devidos[0]}/{revisados_devidos[1]}",
        "taxa_reclassificacao": round(reclass / avaliadas, 2) if avaliadas >= n else None,
        "contestacoes_de_classificacao": contestacoes if contestacoes >= n or contestacoes == 0 else f"<{n}",
        "possivel_subnotificacao": [f"{t}: sem registro no período — possível subnotificação a verificar em campo" for t in subnotificacao],
        "leitura": "O painel informa, não decide: a interpretação de padrões é sempre humana e contextual.",
    }
    audit.registrar(db, "acesso", "painel:indicadores", ator.rotulo, {"dias": dias})
    return resultado
