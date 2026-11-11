from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from app.api.integracoes import _qr, nome_instancia
from app.config import get_settings
from app.integrations.evolution import EventoConexao, EventoMensagem, interpretar_evento
from app.security import gerar_state_oauth, validar_state_oauth


@pytest.fixture(autouse=True)
def chave(monkeypatch):
    monkeypatch.setattr(get_settings(), "chave_criptografia", Fernet.generate_key().decode())


# --- state do OAuth --------------------------------------------------------------
def test_state_ida_e_volta():
    org = uuid4()
    assert validar_state_oauth(gerar_state_oauth(org)) == org


def test_state_forjado_e_recusado():
    with pytest.raises(ValueError):
        validar_state_oauth("qualquer-coisa")


def test_state_expirado(monkeypatch):
    import app.security as sec

    state = gerar_state_oauth(uuid4())
    monkeypatch.setattr(sec, "STATE_VALIDADE_S", -1)
    with pytest.raises(ValueError):
        validar_state_oauth(state)


def test_states_diferentes_para_o_mesmo_organizador():
    org = uuid4()
    assert gerar_state_oauth(org) != gerar_state_oauth(org)


# --- Evolution ----------------------------------------------------------------------
def test_nome_instancia_estavel():
    org = uuid4()
    assert nome_instancia(org) == nome_instancia(org)
    assert nome_instancia(org).startswith("bora-")


def test_qr_remove_prefixo_data_url():
    assert _qr({"base64": "data:image/png;base64,AAAA"}) == "AAAA"
    assert _qr({"qrcode": {"base64": "BBBB"}}) == "BBBB"
    assert _qr({}) is None


@pytest.mark.parametrize(
    ("estado", "esperado"),
    [("open", "CONECTADO"), ("connecting", "AGUARDANDO_QR"), ("close", "DESCONECTADO")],
)
def test_evento_conexao(estado, esperado):
    ev = interpretar_evento(
        {"event": "connection.update", "instance": "bora-abc", "data": {"state": estado}}
    )
    assert ev == EventoConexao("bora-abc", esperado)


def test_evento_conexao_formato_antigo():
    ev = interpretar_evento(
        {"event": "CONNECTION_UPDATE", "instance": "x", "data": {"state": "open"}}
    )
    assert ev == EventoConexao("x", "CONECTADO")


@pytest.mark.parametrize(
    ("status", "esperado"),
    [("SERVER_ACK", "ENVIADA"), ("DELIVERY_ACK", "ENTREGUE"), ("READ", "LIDA")],
)
def test_evento_mensagem(status, esperado):
    ev = interpretar_evento({"event": "messages.update", "data": {"keyId": "M1", "status": status}})
    assert ev == EventoMensagem("M1", esperado)


def test_evento_mensagem_com_key_e_lista():
    ev = interpretar_evento(
        {"event": "messages.update", "data": [{"key": {"id": "M2"}, "status": "DELIVERY_ACK"}]}
    )
    assert ev == EventoMensagem("M2", "ENTREGUE")


@pytest.mark.parametrize(
    "payload",
    [
        {"event": "messages.upsert", "data": {}},
        {"event": "connection.update", "data": {"state": "open"}},  # sem instância
        {"event": "messages.update", "data": {"keyId": "M1", "status": "PENDING"}},
        {},
    ],
)
def test_eventos_ignorados(payload):
    assert interpretar_evento(payload) is None
