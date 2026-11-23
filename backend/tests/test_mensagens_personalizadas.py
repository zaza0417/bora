from decimal import Decimal

from app.domain.mensagens import TEMPLATES_PADRAO, TipoMensagem, renderizar, templates_do_evento


def test_texto_personalizado_substitui_o_padrao():
    tpl = templates_do_evento({"CONVITE": "  Bora, {nome}? {link}  "})
    assert tpl == {TipoMensagem.CONVITE: ["Bora, {nome}? {link}"]}
    texto = renderizar(TipoMensagem.CONVITE, {"nome": "Ana", "link": "x.y/c/1"}, tpl)
    assert texto == "Bora, Ana? x.y/c/1"


def test_tipo_sem_personalizacao_usa_padrao():
    tpl = templates_do_evento({"CONVITE": "Oi {nome}"})
    texto = renderizar(TipoMensagem.VESPERA, {"nome": "Ana", "evento": "Festa"}, tpl)
    assert any(texto.startswith(p.split("{")[0]) for p in TEMPLATES_PADRAO[TipoMensagem.VESPERA])


def test_ignora_vazios_e_tipos_desconhecidos():
    assert templates_do_evento({"CONVITE": "   ", "INVENTADO": "x", "LEMBRETE": 3}) == {}
    assert templates_do_evento(None) == {}


def test_variavel_desconhecida_fica_como_esta():
    tpl = templates_do_evento({"LEMBRETE": "Falta {valor} — {apelido}"})
    texto = renderizar(TipoMensagem.LEMBRETE, {"valor": Decimal("30")}, tpl)
    assert texto == "Falta R$ 30,00 — {apelido}"
