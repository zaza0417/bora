from app.integrations.evolution import ContatoWhatsapp, interpretar_contatos


def test_filtra_grupos_lid_e_invalidos():
    brutos = [
        {"remoteJid": "5511987654321@s.whatsapp.net", "pushName": "Ana"},
        {"remoteJid": "120363025@g.us", "pushName": "Grupo da família"},
        {"remoteJid": "123456789012345@lid", "pushName": "Sem número"},
        {"remoteJid": "status@broadcast"},
        {"remoteJid": "123@s.whatsapp.net", "pushName": "Inválido"},
        {"pushName": "Sem jid"},
    ]
    assert interpretar_contatos(brutos) == [ContatoWhatsapp("Ana", "+5511987654321")]


def test_ignora_o_proprio_numero():
    brutos = [
        {"remoteJid": "5511987654321@s.whatsapp.net", "pushName": "Eu"},
        {"remoteJid": "5561991234567@s.whatsapp.net", "pushName": "Bruno"},
    ]
    assert [c.nome for c in interpretar_contatos(brutos, "5511987654321")] == ["Bruno"]
    assert [c.nome for c in interpretar_contatos(brutos, "+5511987654321")] == ["Bruno"]


def test_completa_nono_digito_e_tira_repetidos():
    brutos = [
        {"remoteJid": "556191234567@s.whatsapp.net", "pushName": None},
        {"remoteJid": "5561991234567@s.whatsapp.net", "pushName": "Carla"},
    ]
    assert interpretar_contatos(brutos) == [ContatoWhatsapp("Carla", "+5561991234567")]


def test_prefere_nome_da_agenda_e_descarta_nome_que_e_numero():
    brutos = [
        {"remoteJid": "5511987654321@s.whatsapp.net", "name": "Tia Rosa", "pushName": "Rosinha"},
        {"remoteJid": "5561991234567@s.whatsapp.net", "pushName": "+55 61 99123-4567"},
    ]
    assert interpretar_contatos(brutos) == [
        ContatoWhatsapp("Tia Rosa", "+5511987654321"),
        ContatoWhatsapp(None, "+5561991234567"),
    ]


def test_ordena_com_nome_primeiro():
    brutos = [
        {"remoteJid": "5511900000001@s.whatsapp.net"},
        {"remoteJid": "5511900000002@s.whatsapp.net", "pushName": "zé"},
        {"remoteJid": "5511900000003@s.whatsapp.net", "pushName": "Ângela"},
    ]
    assert [c.nome for c in interpretar_contatos(brutos)] == ["Ângela", "zé", None]
