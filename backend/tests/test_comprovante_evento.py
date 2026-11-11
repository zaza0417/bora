from app.integrations.evolution import EventoMensagemRecebida, interpretar_evento


def _upsert(**extra):
    base = {
        "event": "messages.upsert",
        "instance": "bora-abc",
        "data": {
            "key": {"remoteJid": "5561991234567@s.whatsapp.net", "fromMe": False, "id": "M1"},
            "messageType": "imageMessage",
            "message": {"imageMessage": {"mimetype": "image/jpeg"}},
        },
    }
    base["data"].update(extra)
    return base


def test_imagem_recebida_vira_evento():
    ev = interpretar_evento(_upsert())
    assert isinstance(ev, EventoMensagemRecebida)
    assert ev.remetente == "5561991234567" and ev.id_mensagem == "M1" and not ev.de_mim
    assert ev.tipo_midia == "imageMessage" and ev.instancia == "bora-abc"


def test_pdf_tambem_conta():
    ev = interpretar_evento(
        _upsert(messageType="documentMessage", message={"documentMessage": {}})
    )
    assert isinstance(ev, EventoMensagemRecebida) and ev.tipo_midia == "documentMessage"


def test_texto_e_ignorado():
    assert (
        interpretar_evento(_upsert(messageType="conversation", message={"conversation": "oi"}))
        is None
    )


def test_grupo_e_ignorado():
    p = _upsert()
    p["data"]["key"]["remoteJid"] = "120363@g.us"
    assert interpretar_evento(p) is None


def test_lista_de_mensagens():
    p = _upsert()
    p["data"] = [p["data"]]
    assert isinstance(interpretar_evento(p), EventoMensagemRecebida)
