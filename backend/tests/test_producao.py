"""Configuração de produção, IP atrás de proxy e paridade das migrações."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from conftest import registro_basico
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from escuta import services
from escuta.config import ConfiguracaoInsegura, Settings, get_settings, set_settings, validar_producao
from escuta.models import Base

CHAVES_PROD = json.dumps({"k-campo-7f3a": {"papel": "agente_campo", "id": "campo-01", "territorio": "MG"}})
FERNET = "x" * 43 + "="


def _prod(monkeypatch, **kw) -> Settings:
    monkeypatch.setenv("ESCUTA_CHAVES_ACESSO", kw.pop("chaves", CHAVES_PROD))
    base = dict(ambiente="producao", database_url="sqlite:////data/escuta.db", chave_cifra=FERNET,
                confiar_proxy=True, segredo_proxy="segredo-netlify")
    base.update(kw)
    return Settings(**base)


def test_producao_valida_passa(monkeypatch):
    validar_producao(_prod(monkeypatch))


@pytest.mark.parametrize("ajuste,trecho", [
    ({"chave_cifra": None}, "ESCUTA_CHAVE_CIFRA"),
    ({"chaves": json.dumps({"campo-dev": {"papel": "agente_campo", "id": "x"}})}, "-dev"),
    ({"segredo_proxy": None}, "ESCUTA_SEGREDO_PROXY"),
    ({"database_url": "sqlite://"}, "memória"),
])
def test_producao_recusa_configuracao_insegura(monkeypatch, ajuste, trecho):
    with pytest.raises(ConfiguracaoInsegura, match=trecho):
        validar_producao(_prod(monkeypatch, **ajuste))


def test_producao_sem_chaves_de_acesso_explicitas(monkeypatch):
    s = _prod(monkeypatch)
    monkeypatch.delenv("ESCUTA_CHAVES_ACESSO")
    with pytest.raises(ConfiguracaoInsegura, match="ESCUTA_CHAVES_ACESSO"):
        validar_producao(s)


def test_app_nao_sobe_em_producao_insegura(monkeypatch):
    from escuta.api.app import app

    set_settings(_prod(monkeypatch, chave_cifra=None))
    with pytest.raises(ConfiguracaoInsegura):
        with TestClient(app):
            pass


# ---------------------------------------------------------------- IP do cliente

def _jwt_netlify(segredo: str, iss: str = "netlify") -> str:
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    cab = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    corpo = b64(json.dumps({"iss": iss, "site_url": "https://alocomunidade.netlify.app", "exp": time.time() + 60}).encode())
    sig = b64(hmac.new(segredo.encode(), f"{cab}.{corpo}".encode(), hashlib.sha256).digest())
    return f"{cab}.{corpo}.{sig}"


class _Req:
    def __init__(self, headers: dict, host: str = "10.0.0.1"):
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.client = type("C", (), {"host": host})()


def _ip(headers, **cfg):
    from escuta.api.app import ip_cliente

    s = get_settings()
    for k, v in cfg.items():
        setattr(s, k, v)
    return ip_cliente(_Req(headers))


def test_ip_sem_confiar_proxy_ignora_cabecalhos():
    assert _ip({"Fly-Client-IP": "1.1.1.1", "X-Nf-Client-Connection-Ip": "2.2.2.2"}, confiar_proxy=False) == "10.0.0.1"


def test_ip_via_netlify_assinado():
    h = {"x-nf-sign": _jwt_netlify("s3gr3d0"), "x-nf-client-connection-ip": "200.1.2.3", "fly-client-ip": "3.3.3.3"}
    assert _ip(h, confiar_proxy=True, segredo_proxy="s3gr3d0") == "200.1.2.3"


@pytest.mark.parametrize("assinatura", ["forjada.aaa.bbb", None, "SEGREDO_ERRADO"])
def test_ip_netlify_forjado_cai_para_fly_client_ip(assinatura):
    token = _jwt_netlify("outro") if assinatura == "SEGREDO_ERRADO" else assinatura
    h = {"x-nf-client-connection-ip": "6.6.6.6", "fly-client-ip": "177.4.5.6"}
    if token:
        h["x-nf-sign"] = token
    assert _ip(h, confiar_proxy=True, segredo_proxy="s3gr3d0") == "177.4.5.6"


def test_ip_netlify_com_emissor_errado_rejeitado():
    h = {"x-nf-sign": _jwt_netlify("s3gr3d0", iss="atacante"), "x-nf-client-connection-ip": "6.6.6.6", "fly-client-ip": "177.4.5.6"}
    assert _ip(h, confiar_proxy=True, segredo_proxy="s3gr3d0") == "177.4.5.6"


def test_limite_de_tentativas_nao_mistura_clientes_atras_do_mesmo_proxy(client):
    s = get_settings()
    s.confiar_proxy, s.segredo_proxy = True, "s3gr3d0"
    r = registro_basico(client)
    via = lambda ip: {"x-nf-sign": _jwt_netlify("s3gr3d0"), "x-nf-client-connection-ip": ip, "fly-client-ip": "3.3.3.3"}  # noqa: E731
    for i in range(10):
        client.get(f"/status/{r['protocolo']}", params={"codigo": f"{i:06d}"}, headers=via("200.0.0.1"))
    assert client.get(f"/status/{r['protocolo']}", params={"codigo": r["codigo_consulta"]}, headers=via("200.0.0.1")).status_code == 429
    ok = client.get(f"/status/{r['protocolo']}", params={"codigo": r["codigo_consulta"]}, headers=via("200.0.0.2"))
    assert ok.status_code == 200
    services._TENTATIVAS.clear()


# ---------------------------------------------------------------- migrações

def test_alembic_upgrade_gera_o_schema_dos_modelos(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    url = f"sqlite:///{tmp_path / 'm.db'}"
    env = {"ESCUTA_DATABASE_URL": url, "PATH": "/usr/bin:/bin:/usr/local/bin"}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    insp = inspect(create_engine(url))
    tabelas = set(insp.get_table_names()) - {"alembic_version"}
    assert tabelas == set(Base.metadata.tables)
    for nome, tabela in Base.metadata.tables.items():
        assert {c["name"] for c in insp.get_columns(nome)} == {c.name for c in tabela.columns}, nome
    check = subprocess.run([sys.executable, "-m", "alembic", "check"], cwd=backend, env=env, capture_output=True, text=True)
    assert check.returncode == 0, check.stdout + check.stderr
