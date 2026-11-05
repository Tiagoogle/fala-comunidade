"""Rotação de chave, retenção/descarte e direitos do titular (LGPD art. 18)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from conftest import CAMPO, GOVERNANCA, REVISOR, SIGILO, conversar, registro_basico
from cryptography.fernet import Fernet
from sqlalchemy import select, text

from escuta import audit, crypto, retention
from escuta.admin import rotacionar_chave
from escuta.config import get_settings
from escuta.db import ViolacaoImutabilidade
from escuta.models import Anexo, Consentimento, EventoStatus, ItemFilaHumana, Manifestacao, Pessoa, TurnoConversa

DPO = {"X-Chave-Acesso": "dpo-dev"}


def _usar_chaves(*chaves: str) -> None:
    get_settings().chave_cifra = ",".join(chaves)
    crypto.reset()


def _caso_completo(client) -> dict:
    """Caso identificado, com anexo e conversa — tudo o que é cifrado."""
    r = registro_basico(client, modo_identificacao="identificado", nome="Marta Souza", contato="31 98888-7777")
    up = client.post(f"/manifestacoes/{r['id']}/anexos", files={"arquivo": ("foto.jpg", b"\xff\xd8 conteudo da foto", "image/jpeg")}, headers=CAMPO)
    assert up.status_code == 200
    conversar(client, ["O bueiro da praça entupiu de novo."])
    return r


# ---------------------------------------------------------------- rotação de chave

def test_rotacao_completa_sem_perda(client, db):
    a, b = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    _usar_chaves(a)
    r = _caso_completo(client)
    _usar_chaves(b, a)  # nova primeiro: novos dados já saem com B, antigos ainda decifram com A
    assert client.get(f"/manifestacoes/{r['id']}/contato", params={"motivo": "retorno"}, headers=REVISOR).json()["contato"] == "31 98888-7777"
    cont = rotacionar_chave(db)
    db.commit()
    assert cont == {"pessoas": 1, "turnos": 2, "anexos": 1}
    _usar_chaves(b)  # chave antiga removida
    assert client.get(f"/manifestacoes/{r['id']}/contato", params={"motivo": "retorno"}, headers=REVISOR).json()["nome"] == "Marta Souza"
    an_id = db.execute(select(Anexo.id_anexo)).scalar_one()
    assert client.get(f"/anexos/{an_id}", params={"motivo": "conferência"}, headers=REVISOR).content == b"\xff\xd8 conteudo da foto"
    db.expire_all()
    assert all(crypto.decifrar_texto(t.texto) for t in db.execute(select(TurnoConversa)).scalars())
    assert audit.verificar_cadeia(db).integra


def test_rotacao_idempotente(client, db):
    a, b = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    _usar_chaves(a)
    _caso_completo(client)
    _usar_chaves(b, a)
    rotacionar_chave(db)
    db.commit()
    rotacionar_chave(db)  # segunda execução não estraga nada
    db.commit()
    _usar_chaves(b)
    p = db.execute(select(Pessoa)).scalar_one()
    assert crypto.decifrar_texto(p.contato_cifrado) == "31 98888-7777"


def test_remover_chave_antiga_sem_rotacionar_falha_explicitamente(client, db):
    a, b = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    _usar_chaves(a)
    _caso_completo(client)
    _usar_chaves(b)  # erro operacional: tirou a antiga antes de rotacionar
    p = db.execute(select(Pessoa)).scalar_one()
    with pytest.raises(crypto.ChaveIndisponivel):
        crypto.decifrar_texto(p.contato_cifrado)
    with pytest.raises(crypto.ChaveIndisponivel):
        rotacionar_chave(db)  # recusa, e nada é sobrescrito
    db.rollback()
    id_m = db.execute(select(Manifestacao.id_manifestacao)).scalar_one()
    r = client.get(f"/manifestacoes/{id_m}/contato", params={"motivo": "retorno"}, headers=REVISOR)
    assert r.status_code == 503 and "rotação incompleta" in r.json()["detail"]
    db.rollback()
    _usar_chaves(a)
    assert crypto.decifrar_texto(db.execute(select(Pessoa)).scalar_one().contato_cifrado) == "31 98888-7777"


def test_producao_recusa_chave_invalida_na_lista(monkeypatch):
    from escuta.config import ConfiguracaoInsegura, Settings, validar_producao

    monkeypatch.setenv("ESCUTA_CHAVES_ACESSO", '{"k-x": {"papel": "revisor", "id": "r"}}')
    s = Settings(ambiente="producao", chave_cifra=Fernet.generate_key().decode() + ",nao-e-chave", segredo_proxy="s",
                 database_url="sqlite:////data/x.db")
    with pytest.raises(ConfiguracaoInsegura, match="posição 2"):
        validar_producao(s)


# ---------------------------------------------------------------- retenção

def _encerrar(client, db, id_m: str, dias_atras: int) -> None:
    client.post(f"/manifestacoes/{id_m}/avaliacoes", json={"resultado": "confirmada", "justificativa": "procede"}, headers=REVISOR)
    client.post(f"/manifestacoes/{id_m}/status", json={"status": "encerrada", "justificativa": "respondido ao autor por telefone"}, headers=REVISOR)
    db.expire_all()
    for ev in db.execute(select(EventoStatus).where(EventoStatus.id_manifestacao == id_m, EventoStatus.status == "encerrada")).scalars():
        db.execute(text("UPDATE evento_status SET criado_em = :t WHERE id_evento_status = :i"),
                   {"t": (ev.criado_em - timedelta(days=dias_atras)).isoformat(sep=" "), "i": ev.id_evento_status})
    db.commit()


def test_sem_politica_nada_e_descartado(client, db):
    r = _caso_completo(client)
    _encerrar(client, db, r["id"], 4000)
    out = retention.aplicar_retencao(db)
    assert out["pendentes_de_definicao"] == ["contato", "turnos_conversa", "conteudo_e_anexos"]
    assert out["contatos_removidos"] == out["conteudos_descartados"] == 0


def test_retencao_respeita_prazo_aberto_e_guarda(client, db, tmp_path):
    get_settings().retencao = {"contato": 180, "conteudo_e_anexos": 1825}
    vencido = _caso_completo(client)
    _encerrar(client, db, vencido["id"], 2000)
    recente = registro_basico(client, relato="Buraco recente.", modo_identificacao="identificado", nome="Ana", contato="31 1")
    _encerrar(client, db, recente["id"], 10)
    aberto = registro_basico(client, relato="Caso ainda aberto.", modo_identificacao="identificado", nome="Rui", contato="31 2")
    guardado = registro_basico(client, relato="Caso sob obrigação de guarda.")
    _encerrar(client, db, guardado["id"], 4000)
    assert client.post("/dpo/retencao", json={"protocolo": guardado["protocolo"], "suspensa": True, "justificativa": "ação judicial em curso"}, headers=DPO).status_code == 200

    out = retention.aplicar_retencao(db)
    db.commit()
    db.expire_all()
    assert out["contatos_removidos"] == 1 and out["conteudos_descartados"] == 1 and out["anexos_descartados"] == 1
    assert out["suspensos_por_obrigacao_de_guarda"] == 1

    m = db.get(Manifestacao, vencido["id"])
    assert m.conteudo_original.startswith("[conteúdo descartado") and m.hash_original and m.descartado_em
    assert db.get(Pessoa, m.id_pessoa).contato_cifrado is None
    assert not list((tmp_path / "anexos").iterdir())  # arquivo do anexo removido
    assert db.get(Manifestacao, recente["id"]).descartado_em is None
    assert db.get(Manifestacao, aberto["id"]).descartado_em is None
    assert db.get(Manifestacao, guardado["id"]).conteudo_original == "Caso sob obrigação de guarda."
    tipos = [e for e in db.execute(text("SELECT tipo_evento FROM evento_auditoria")).scalars()]
    assert "descarte" in tipos and "retencao" in tipos
    assert audit.verificar_cadeia(db).integra
    assert retention.aplicar_retencao(db)["conteudos_descartados"] == 0  # idempotente


def test_descarte_fora_da_rotina_continua_bloqueado(client, db):
    from escuta.models import agora

    r = registro_basico(client)
    m = db.get(Manifestacao, r["id"])
    m.descartado_em = agora()  # sem session.info["descarte_autorizado"]
    m.conteudo_original = "tentativa de apagar por fora"
    with pytest.raises(ViolacaoImutabilidade):
        db.flush()


def test_retencao_de_turnos_de_conversa(client, db):
    get_settings().retencao = {"turnos_conversa": 90}
    conversar(client, ["Quero saber quando a obra termina?"])
    db.execute(text("UPDATE sessao_conversa SET atualizada_em = '2020-01-01 00:00:00'"))
    db.commit()
    out = retention.aplicar_retencao(db)
    db.commit()
    assert out["turnos_descartados"] == 2
    assert all(crypto.decifrar_texto(t.texto) == retention.MARCADOR_TURNO for t in db.execute(select(TurnoConversa)).scalars())


def test_rotinas_inclui_retencao(client):
    assert "retencao" in client.post("/admin/rotinas", headers=GOVERNANCA).json()


# ---------------------------------------------------------------- titular

def _cred(r: dict) -> dict:
    return {"protocolo": r["protocolo"], "codigo": r["codigo_consulta"]}


def test_titular_acesso_exporta_proprios_dados(client):
    a = registro_basico(client, relato="Poeira na minha casa.", modo_identificacao="identificado", nome="Marta", contato="31 98888-7777")
    registro_basico(client, relato="Outro caso, de outra pessoa.", modo_identificacao="identificado", nome="Zé", contato="31 90000-0000")
    r = client.post("/titular/acesso", json=_cred(a))
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    d = r.json()
    assert d["seus_dados_de_contato"]["contato"] == "31 98888-7777" and d["relato_original"] == "Poeira na minha casa."
    assert "Zé" not in str(d) and "outra pessoa" not in str(d)
    assert "não é decisão" in d["classificacao"]["como_foi_feita"]
    assert any(c["finalidade"] == "tratamento_manifestacao" for c in d["consentimentos"])


def test_titular_credencial_errada_indistinta_e_limitada(client):
    a = registro_basico(client)
    errado = client.post("/titular/acesso", json={"protocolo": a["protocolo"], "codigo": "000000"})
    inexistente = client.post("/titular/acesso", json={"protocolo": "2026-MG-999999", "codigo": "000000"})
    assert errado.status_code == inexistente.status_code == 404 and errado.json() == inexistente.json()
    for i in range(8):
        client.post("/titular/acesso", json={"protocolo": a["protocolo"], "codigo": f"{i:06d}"})
    assert client.post("/titular/acesso", json=_cred(a)).status_code == 429  # limite compartilhado com /status


def test_titular_correcao_vira_adendo_e_reavalia(client, db):
    a = registro_basico(client, relato="Poeira no quintal.")
    r = client.post("/titular/correcao", json=_cred(a) | {"texto": "Corrijo: a água que a gente usa pra beber ficou com cor estranha."})
    assert r.status_code == 200 and r.json()["versao"] == 1
    m = db.get(Manifestacao, a["id"])
    assert m.conteudo_original == "Poeira no quintal." and m.adendos[0].autor == "titular:titular"
    assert m.prioridade_sugerida == "P2" and m.revisao_obrigatoria


def test_titular_revoga_avisos(client, db):
    a = registro_basico(client, consentimento_notificacoes=True)
    r = client.post("/titular/consentimento/revogar", json=_cred(a) | {"finalidade": "notificacoes"})
    assert r.status_code == 200 and "não vai mais receber avisos" in r.json()["mensagem"]
    ativos = db.execute(select(Consentimento).where(Consentimento.finalidade == "notificacoes", Consentimento.revogacao_em.is_(None))).scalars().all()
    assert ativos == []


def test_titular_revoga_tratamento_apaga_contato_e_aciona_dpo(client, db):
    a = registro_basico(client, modo_identificacao="identificado", nome="Marta", contato="31 98888-7777")
    r = client.post("/titular/consentimento/revogar", json=_cred(a) | {"finalidade": "tratamento_manifestacao", "motivo": "não confio mais"})
    assert r.status_code == 200 and "contato foram apagados" in r.json()["mensagem"] and r.json()["prazo_resposta"]
    p = db.execute(select(Pessoa)).scalar_one()
    assert p.contato_cifrado is None and p.nome_cifrado is None and p.dados_removidos_em
    assert db.get(Manifestacao, a["id"]).conteudo_original  # conteúdo NÃO é apagado automaticamente
    fila_dpo = client.get("/fila", headers=DPO).json()
    assert len(fila_dpo) == 1 and fila_dpo[0]["motivo"] == "direito_titular" and "prazo legal" in fila_dpo[0]["contexto"]


def test_pedido_do_titular_so_aparece_para_o_dpo(client):
    a = registro_basico(client)
    r = client.post("/titular/pedido", json=_cred(a) | {"tipo": "revisao_humana", "detalhe": "Meu telefone é 31 97777-6666, me liguem"})
    assert r.status_code == 200 and "prazo legal" in r.json()["mensagem"]
    assert all(i["motivo"] != "direito_titular" for i in client.get("/fila", headers=REVISOR).json())
    dpo = client.get("/fila", headers=DPO).json()
    assert len(dpo) == 1 and "97777" not in dpo[0]["contexto"]  # detalhe mascarado na fila
    item = dpo[0]["id"]
    assert client.post(f"/fila/{item}/assumir", headers=REVISOR).status_code == 403
    assert client.post(f"/fila/{item}/assumir", headers=DPO).status_code == 200


def test_dpo_nao_le_conteudo_nem_age_fora_do_papel(client):
    sig = registro_basico(client, relato="Quero denunciar despejo de rejeito no córrego à noite.")
    assert sig["rota"] == "sigilosa"
    assert client.get(f"/manifestacoes/{sig['id']}", headers=DPO).status_code == 403
    assert client.get(f"/manifestacoes/{sig['id']}", headers=SIGILO).status_code == 200
    assert client.post("/dpo/retencao", json={"protocolo": sig["protocolo"], "suspensa": True, "justificativa": "x y z"}, headers=REVISOR).status_code == 403
    assert client.post("/dpo/anonimizar-contato", json={"protocolo": sig["protocolo"], "justificativa": "pedido"}, headers=DPO).json() == {"contato_removido": False}


def test_correcao_bloqueada_apos_descarte(client, db):
    get_settings().retencao = {"conteudo_e_anexos": 30}
    a = registro_basico(client)
    _encerrar(client, db, a["id"], 60)
    retention.aplicar_retencao(db)
    db.commit()
    r = client.post("/titular/correcao", json=_cred(a) | {"texto": "complemento"})
    assert r.status_code == 422 and "descartado" in r.json()["detail"]
