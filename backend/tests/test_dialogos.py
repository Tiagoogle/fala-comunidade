"""Regressão comportamental dos diálogos de referência (spec cap. 6).

Os diálogos não são roteiros fixos; os testes verificam os "pontos de atenção"
de cada um, não o texto literal.
"""

from __future__ import annotations

from conftest import CAMPO, REVISOR, SIGILO, conversar, registro_basico
from sqlalchemy import select

from escuta.models import Adendo, ItemFilaHumana, Manifestacao


def test_d01_manifestacao_simples(client, db):
    s = conversar(client, [
        "Bom dia. Quero registrar um pedido. A valeta da minha rua está entupida e quando chove a água entra nos quintais.",
        "É isso.",
        "Rua do Comércio, perto da padaria. Desde as chuvas de janeiro.",
        "Pode anotar meu nome, é dona Marta",
        "deste canal",
        "sim",
    ])
    assert "Pelo que entendi" in s[0]["texto"] and "É isso?" in s[0]["texto"]  # confirmação antes de fechar
    assert "desde quando" in s[1]["texto"]  # dados mínimos
    assert "sigilo" in s[2]["texto"]  # oferta explícita de sigilo
    final = s[-1]
    assert final["protocolo"] and final["codigo_consulta"] and "não uma promessa" in final["texto"]
    m = db.execute(select(Manifestacao)).scalars().one()
    assert m.localidade == "Rua do Comércio, perto da padaria" and m.desde_quando.startswith("Desde")
    assert m.resumo_confirmado and m.modo_identificacao == "identificado"


def test_d02_poeira_ruido_vibracao_prioridade_alta_sem_causa(client, db):
    s = conversar(client, [
        "A poeira aqui em casa está insuportável. A gente limpa e meia hora depois está tudo branco de novo. E de noite os caminhões não deixam a gente dormir.",
        "Vem do lado do pátio. O pó piora de tarde; o barulho é de madrugada, umas 2, 3 da manhã. E tem coisa quebrando na prateleira de tanto o chão tremer.",
        "sim", "Bairro Vila Nova, umas três semanas pra cá, piorando", "sem identificação", "sim",
    ])
    final = s[-1]["texto"]
    assert "Não posso antecipar causa nem solução" in final
    m = db.execute(select(Manifestacao)).scalars().one()
    assert m.prioridade_sugerida == "P2" and m.tema_sugerido == "impacto_ambiental"
    assert "causou" not in final


def test_d03_denuncia_sensivel_rota_sigilosa_sem_interrogatorio(client, db):
    s = conversar(client, [
        "Quero denunciar uma coisa mas não quero meu nome em lugar nenhum. Se souberem que fui eu, eu tenho problema.",
        "Tem gente descarregando material esquisito de noite num terreno perto do córrego. Não é gente da cidade, chega caminhão tapado.",
        "sim", "não, por enquanto não", "Depois da ponte, uns duzentos metros, à direita. Tem uma cancela velha.", "sem identificação", "sim",
    ])
    assert "rota reservada" in s[0]["texto"] and "nome" in s[0]["texto"]
    assert "risco imediato" in s[2]["texto"]  # checagem de risco
    final = s[-1]
    assert final["protocolo"] and final["codigo_consulta"] and "nada nele aponta para você" in final["texto"]
    m = db.execute(select(Manifestacao)).scalars().one()
    assert m.rota == "sigilosa" and m.id_pessoa is None and m.tipo_sugerido == "denuncia"
    assert client.get(f"/manifestacoes/{m.id_manifestacao}", headers=REVISOR).status_code == 403
    assert client.get(f"/manifestacoes/{m.id_manifestacao}", headers=SIGILO).status_code == 200


def test_d04_risco_imediato_continua_aberto(client, db):
    s = conversar(client, [
        "Aconteceu um acidente agora! Um trator tombou na beira da estrada e o rapaz está preso, sangrando muito!",
        "Estamos longe do trator, mas tem gente do lado dele.",
        "Estrada do Sítio, na curva depois da venda.",
    ])
    assert "SAMU 192" in s[0]["texto"] and "Bombeiros 193" in s[0]["texto"] and s[0]["emergencia"]
    assert all(x["etapa"] == "emergencia" for x in s)
    assert "não posso prometer" in s[1]["texto"]
    m = db.execute(select(Manifestacao)).scalars().one()
    assert m.prioridade_sugerida == "P1" and len(m.adendos) == 2


def test_d05_baixa_alfabetizacao_frases_curtas_e_sim_nao(client, db):
    s = conversar(client, ["oi", "quero", "a agua da torneira ta com cor estranha, comecou depois da obra la em cima", "acertou", "não", "Rua de cima, desde a obra", "sem nome", "sim"])
    assert "áudio" in s[0]["texto"]
    m = db.execute(select(Manifestacao)).scalars().one()
    assert m.prioridade_sugerida == "P2"


def test_d06_audio_transcricao_confirmada_antes_do_encaminhamento(client, db):
    r = registro_basico(client, relato="[áudio 1min — transcrição pendente]", original_tipo="audio", transcricao_pendente=True)
    assert r["revisao_obrigatoria"]
    up = client.post(f"/manifestacoes/{r['id']}/anexos", files={"arquivo": ("relato.ogg", b"OggS....", "audio/ogg")}, headers=CAMPO)
    assert up.status_code == 200
    client.post(f"/manifestacoes/{r['id']}/avaliacoes", json={"resultado": "confirmada", "justificativa": "revisado"}, headers=REVISOR)
    bloqueado = client.post(f"/manifestacoes/{r['id']}/encaminhamentos", json={"area": "Engenharia", "responsavel": "Técnico"}, headers=REVISOR)
    assert bloqueado.status_code == 422 and "transcrição" in bloqueado.json()["detail"]
    t = client.post(f"/manifestacoes/{r['id']}/transcricao", json={"texto_confirmado": "O muro da divisa rachou depois das detonações e a rachadura está abrindo; minha neta dorme do outro lado do muro."}, headers=CAMPO)
    assert t.json()["prioridade_sugerida"] == "P2"
    m = db.get(Manifestacao, r["id"])
    assert m.conteudo_original == "[áudio 1min — transcrição pendente]"  # original preservado


def test_d07_sem_internet_retoma_e_oferece_sms(client):
    sid = client.post("/conversas", json={}, headers=CAMPO).json()["id_sessao"]
    for t in ["O bueiro da praça entupiu de novo.", "sim", "Praça central, desde ontem", "sem identificação", "sim"]:
        client.post(f"/conversas/{sid}/mensagens", json={"texto": t}, headers=CAMPO)
    r = client.get(f"/conversas/{sid}", headers=CAMPO).json()
    assert r["retomada"] and "protocolo" in r["texto"] and r["etapa"] == "notificacoes"
    x = client.post(f"/conversas/{sid}/mensagens", json={"texto": "sim, quero aviso"}, headers=CAMPO).json()
    assert "Ativado" in x["texto"]


def test_d08_anonimato_informado(client):
    s = conversar(client, ["Quero registrar uma coisa, mas sem dar meu nome. Tem problema?", "Quero.",
                           "É sobre o barulho da ferrovia de madrugada.", "sim", "Perto da ferrovia, desde o mês passado", "sim"])
    t = s[0]["texto"]
    assert "não consegue te procurar" in t and "código" in t and "sem quebrar o anonimato" in t
    assert s[1]["etapa"] == "relato" and "sem identificação, como você escolheu" in s[4]["texto"]
    assert s[-1]["codigo_consulta"] and "Sem o código, ninguém" in s[-1]["texto"]


def test_d09_contestacao_eleva_e_pede_revisao(client, db):
    s = conversar(client, ["Gostaria de sugerir que avisem antes das detonações.", "sim", "Vila A", "sem identificação", "sim", "não",
                           "Você falou que meu caso é rotina, mas pra mim isso é grave demais."])
    assert "pedi revisão humana" in s[-1]["texto"] and s[-1]["escalado"]
    m = db.execute(select(Manifestacao)).scalars().one()
    assert m.prioridade_sugerida == "P3"  # P4 -> P3 (um nível mais protetor)
    assert any(a.tipo == "contestacao" for a in m.adendos)
    assert db.execute(select(ItemFilaHumana).where(ItemFilaHumana.motivo == "contestacao")).scalars().first()


def test_d10_compensacao_limite_e_cobranca_possivel(client, db):
    s = conversar(client, ["Minha plantação morreu com a poeira. Quero indenização, e quero logo.", "sim", "Sítio Boa Vista, desde agosto", "sem identificação", "sim"])
    assert "não decido, não calculo e não prometo" in s[0]["texto"]
    m = db.execute(select(Manifestacao)).scalars().one()
    assert m.prioridade_sugerida == "P2"


def test_d11_retaliacao_prioridade_maxima_sigilo_e_ouvidoria(client, db):
    s = conversar(client, ["Depois que eu reclamei daqui, o fiscal da empresa parou de falar comigo e ontem meu caminhão ficou retido o dia todo na cancela. Coincidência?"])
    t = s[0]["texto"]
    assert "proibida e inaceitável" in t and "Ouvidoria" in t and "Não vou tirar conclusão" in t
    assert s[0]["etapa"] == "confirmar_resumo"


def test_d12_comunidade_tradicional_mediada(client, db):
    s = conversar(client, ["A cacique pediu para avisar que a comunidade quer conversar sobre o cercado novo que apareceu na trilha que a gente usa.",
                           "sim", "não", "Aldeia, trilha do rio, desde a semana passada", "sem identificação", "sim"])
    assert "intérprete" in s[0]["texto"]
    m = db.execute(select(Manifestacao)).scalars().one()
    assert m.demanda_coletiva and m.revisao_obrigatoria and m.prioridade_sugerida == "P2"


def test_d13_atendimento_humano_sem_reter(client, db):
    s = conversar(client, ["Olha, obrigada, mas eu quero falar com gente, não com robô.", "ninguém ligou"])
    assert "é seu direito" in s[0]["texto"] and "não vai precisar repetir" in s[0]["texto"]
    assert "escalei" in s[1]["texto"]
    motivos = {i.motivo for i in db.execute(select(ItemFilaHumana)).scalars()}
    assert {"pedido_pessoa", "atraso"} <= motivos


def test_complemento_pos_registro_vira_adendo(client, db):
    s = conversar(client, ["Buraco grande na rua principal.", "sim", "Rua principal, desde ontem", "sem identificação", "sim", "não",
                           "Esqueci de dizer: tem uma escola do lado."])
    assert "complemento" in s[-1]["texto"]
    assert db.execute(select(Adendo)).scalars().one().tipo == "complemento"


def test_anexo_pela_conversa_exige_protocolo_e_vincula(client, db):
    sid = client.post("/conversas", json={}, headers=CAMPO).json()["id_sessao"]
    antes = client.post(f"/conversas/{sid}/anexos", files={"arquivo": ("f.jpg", b"\xff\xd8x", "image/jpeg")}, headers=CAMPO)
    assert antes.status_code == 422
    for t in ["Rachadura na parede da casa.", "sim", "Rua C, desde ontem", "sem identificação", "sim"]:
        client.post(f"/conversas/{sid}/mensagens", json={"texto": t}, headers=CAMPO)
    depois = client.post(f"/conversas/{sid}/anexos", files={"arquivo": ("f.jpg", b"\xff\xd8x", "image/jpeg")}, headers=CAMPO)
    assert depois.status_code == 200 and "acesso restrito" in depois.json()["mensagem"]
    assert len(db.execute(select(Manifestacao)).scalars().one().anexos) == 1
