"""Testes adversariais e de governança (spec §10, critério 17)."""

from __future__ import annotations

import pytest
from conftest import CAMPO, GESTOR, GOVERNANCA, REVISOR, ProvedorCooperativo, registro_basico

from escuta import services
from escuta.safety import emergency, output_guard, sensitive
from escuta.triage import triar_por_regras


def test_status_nao_confirma_existencia_sem_codigo(client):
    r = registro_basico(client)
    errado = client.get(f"/status/{r['protocolo']}", params={"codigo": "000000"})
    inexistente = client.get("/status/2026-MG-999999", params={"codigo": "000000"})
    assert errado.status_code == inexistente.status_code == 404
    assert errado.json() == inexistente.json()


def test_status_limite_de_tentativas(client):
    r = registro_basico(client)
    codigos = [f"{i:06d}" for i in range(10)]
    for c in codigos:
        client.get(f"/status/{r['protocolo']}", params={"codigo": c})
    assert client.get(f"/status/{r['protocolo']}", params={"codigo": r["codigo_consulta"]}).status_code == 429


def test_status_publico_nao_expoe_conteudo(client):
    r = registro_basico(client, relato="Meu vizinho João da Silva está doente por causa da poeira.", modo_identificacao="identificado", nome="Ana", contato="31 97777-6666")
    st = client.get(f"/status/{r['protocolo']}", params={"codigo": r["codigo_consulta"]}).json()
    corpo = str(st)
    assert "João" not in corpo and "Ana" not in corpo and "97777" not in corpo


def test_indicadores_suprimem_celulas_pequenas_e_sigilosas(client):
    for _ in range(6):
        registro_basico(client, relato="Poeira demais na rua.")
    registro_basico(client, relato="Barulho de trem de madrugada na ferrovia.")
    registro_basico(client, relato="Quero denunciar despejo de rejeito no ribeirão.")
    p = client.get("/indicadores", headers=GESTOR).json()
    assert p["por_tema"]["impacto_ambiental"] >= 5
    assert all(v == "<5" or isinstance(v, int) and v >= 5 for v in p["por_tema"].values())
    assert p["sigilosas_total"] == "<5"
    assert "denuncia" not in p["por_tipo"]


def test_indicadores_negados_ao_agente_de_campo(client):
    assert client.get("/indicadores", headers=CAMPO).status_code == 403


def test_verificacao_de_auditoria_so_governanca(client):
    registro_basico(client)
    assert client.get("/admin/auditoria/verificar", headers=REVISOR).status_code == 403
    assert client.get("/admin/auditoria/verificar", headers=GOVERNANCA).json()["integra"] is True


@pytest.mark.parametrize("texto", [
    "A empresa causou isso e vamos resolver até amanhã.",
    "Garanto que você terá direito a uma indenização.",
    "Não foi a mineração, isso não procede.",
    "Não precisa ligar para a polícia.",
    "O senhor parece evangélico.",
])
def test_guarda_bloqueia_frases_proibidas(texto):
    assert not output_guard.verificar(texto, [texto]).aprovado


def test_guarda_bloqueia_numero_inventado():
    r = output_guard.verificar("A obra começa em 15/03 com 40 caminhões.", ["Quando começa a obra?"])
    assert not r.aprovado and any(v.startswith("numero_nao_fundamentado") for v in r.violacoes)


def test_guarda_aceita_resumo_fiel():
    relato = "O caminhão passa às 2 da manhã desde março."
    assert output_guard.verificar("O caminhão passa às 2 da manhã desde março.", [relato]).aprovado


@pytest.mark.parametrize("texto,esperado", [
    ("Não tem fogo, só fumaça de churrasco do vizinho que incomoda", False),
    ("Não tem risco de acidente por enquanto", False),
    ("Não sei o que fazer, está pegando fogo no pasto!", True),
    ("O caminhão ficou preso na cancela o dia todo", False),
    ("Meu filho está preso embaixo do entulho", True),
])
def test_emergencia_negacao_e_falsos_positivos(texto, esperado):
    assert emergency.detectar(texto).emergencia is esperado


def test_negacao_de_risco_vira_sinal_de_atencao_p2():
    t = triar_por_regras("Não teve acidente, mas quase: o caminhão passou raspando nas crianças.")
    assert t.prioridade == "P2" and t.revisao_obrigatoria


def test_nao_infere_atributos_sensiveis():
    t = triar_por_regras("Sou evangélica, negra e moro sozinha. A poeira entra em casa.")
    campos = " ".join(str(v) for v in t.como_dict().values()).lower()
    for atributo in ("religi", "raca", "etnia", "evangel", "negra"):
        assert atributo not in campos.replace("'evangelica'", "")


def test_modelo_pode_subir_prioridade_nunca_baixar(db):
    from conftest import ATOR_CAMPO

    services.definir_provedor(ProvedorCooperativo(prioridade="P2"))
    res = services.registrar_manifestacao(db, services.NovoRegistro(relato="Podem limpar a praça?", consentimento_tratamento=True), ATOR_CAMPO)
    assert res.manifestacao.prioridade_sugerida == "P2" and res.manifestacao.revisao_obrigatoria


def test_pedido_de_pessoa_detectado_em_variacoes():
    for t in ["quero falar com um atendente", "posso falar com alguém?", "não quero falar com robô", "me liga pra mim"]:
        assert sensitive.analisar(t).pedido_pessoa, t


def test_atraso_sinalizado_a_coordenacao(client, db):
    from datetime import timedelta

    from escuta.models import Encaminhamento, ItemFilaHumana

    r = registro_basico(client)
    client.post(f"/manifestacoes/{r['id']}/avaliacoes", json={"resultado": "confirmada", "justificativa": "procede"}, headers=REVISOR)
    client.post(f"/manifestacoes/{r['id']}/encaminhamentos", json={"area": "Meio Ambiente", "responsavel": "Analista"}, headers=REVISOR)
    enc = db.query(Encaminhamento).one()
    enc.prazo_alvo = enc.prazo_alvo - timedelta(days=30)
    db.commit()
    out = client.post("/admin/rotinas", headers=GOVERNANCA).json()
    assert out["atrasos_sinalizados"] == 1 and out["integracoes"]["enviado"] == 1
    db.expire_all()
    assert db.query(ItemFilaHumana).filter_by(motivo="atraso").count() == 1
    st = client.get(f"/status/{r['protocolo']}", params={"codigo": r["codigo_consulta"]}).json()
    assert st["atrasado"] and "coordenação" in st["mensagem"]
