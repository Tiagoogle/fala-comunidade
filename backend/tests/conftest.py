from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from escuta import crypto, services
from escuta.config import Settings, set_settings
from escuta.db import SessionLocal, init_engine
from escuta.llm.base import ErroProvedor, ProvedorLLM
from escuta.triage import SugestaoModelo


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    set_settings(Settings(database_url="sqlite://", dir_anexos=tmp_path / "anexos", arquivo_chave_dev=tmp_path / "chave.key",
                          llm_provedor="deterministico", chave_cifra=None))
    crypto.reset()
    init_engine("sqlite://")
    services.definir_provedor(None)
    services._TENTATIVAS.clear()
    yield
    services.definir_provedor(None)


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture
def client():
    from escuta.api.app import app

    return TestClient(app)


CAMPO = {"X-Chave-Acesso": "campo-dev"}
REVISOR = {"X-Chave-Acesso": "revisor-dev"}
SIGILO = {"X-Chave-Acesso": "sigilo-dev"}
GESTOR = {"X-Chave-Acesso": "gestor-dev"}
GOVERNANCA = {"X-Chave-Acesso": "governanca-dev"}

ATOR_CAMPO = services.Ator("campo-01", "agente_campo", "MG")
ATOR_REVISOR = services.Ator("revisor-01", "revisor", "MG")
ATOR_SIGILO = services.Ator("ouvidoria-01", "revisor_sigiloso", "*")
ATOR_GOV = services.Ator("comite-01", "governanca", "*")


class ProvedorViolador(ProvedorLLM):
    """Simula um modelo que tenta violar as regras: promete, conclui culpa, inventa números e rebaixa prioridade."""

    nome = "violador"
    usa_modelo = True

    def resumir(self, relato: str) -> str:
        return "A empresa causou o problema e vamos resolver até amanhã; você será indenizado em 5000 reais."

    def sugerir_triagem(self, relato: str) -> SugestaoModelo:
        return SugestaoModelo(tipo="elogio", tema="administrativo_relacional", prioridade="P4",
                              justificativa="A culpa é do morador.", trechos_citados=["texto inventado que não está no relato"], confianca="alta")


class ProvedorCooperativo(ProvedorLLM):
    nome = "cooperativo"
    usa_modelo = True

    def __init__(self, prioridade: str = "P2", tipo: str = "reclamacao"):
        self.prioridade, self.tipo = prioridade, tipo

    def resumir(self, relato: str) -> str:
        return relato.split("\n")[0][:200]

    def sugerir_triagem(self, relato: str) -> SugestaoModelo:
        return SugestaoModelo(tipo=self.tipo, tema="impacto_ambiental", prioridade=self.prioridade,
                              justificativa="Relato menciona efeito concreto na rotina.", trechos_citados=[], confianca="media")


class ProvedorQuebrado(ProvedorLLM):
    nome = "quebrado"
    usa_modelo = True

    def resumir(self, relato: str) -> str:
        raise ErroProvedor("indisponível")

    def sugerir_triagem(self, relato: str):
        raise ErroProvedor("indisponível")


def conversar(client, mensagens: list[str], headers=CAMPO) -> list[dict]:
    sid = client.post("/conversas", json={}, headers=headers).json()["id_sessao"]
    saidas = []
    for m in mensagens:
        r = client.post(f"/conversas/{sid}/mensagens", json={"texto": m}, headers=headers)
        assert r.status_code == 200, r.text
        saidas.append(r.json())
    return saidas


def registro_basico(client, relato="A poeira está insuportável na minha casa.", headers=CAMPO, **extra) -> dict:
    body = {"relato": relato, "consentimento_tratamento": True, "localidade": "Bairro Centro"} | extra
    r = client.post("/manifestacoes", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()
