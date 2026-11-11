import pytest

from app.domain.estados import AcaoConvidado as A
from app.domain.estados import StatusConvidado as S
from app.domain.estados import TransicaoInvalida, transicionar


@pytest.mark.parametrize(
    ("atual", "acao", "contrib", "esperado"),
    [
        (S.CONVIDADO, A.ACEITAR, True, S.AGUARDANDO_PAGAMENTO),
        (S.CONVIDADO, A.ACEITAR, False, S.CONFIRMADO),
        (S.CONVIDADO, A.RECUSAR, True, S.RECUSOU),
        (S.RECUSOU, A.ACEITAR, True, S.AGUARDANDO_PAGAMENTO),
        (S.AGUARDANDO_PAGAMENTO, A.PAGAMENTO_APROVADO, True, S.CONFIRMADO),
        (S.CONVIDADO, A.PAGAMENTO_APROVADO, True, S.CONFIRMADO),
        (S.AGUARDANDO_PAGAMENTO, A.BAIXA_MANUAL, True, S.CONFIRMADO),
        (S.CONFIRMADO, A.ESTORNO, True, S.AGUARDANDO_PAGAMENTO),
        (S.CONFIRMADO, A.RECUSAR, False, S.RECUSOU),
        (S.AGUARDANDO_PAGAMENTO, A.ACEITAR, True, S.AGUARDANDO_PAGAMENTO),
    ],
)
def test_transicoes_validas(atual, acao, contrib, esperado):
    assert transicionar(atual, acao, tem_contribuicao=contrib) == esperado


@pytest.mark.parametrize(
    ("atual", "acao", "contrib"),
    [
        (S.CONFIRMADO, A.RECUSAR, True),  # já pagou → falar com organizador
        (S.AGUARDANDO_PAGAMENTO, A.ESTORNO, True),
        (S.CONVIDADO, A.PAGAMENTO_APROVADO, False),
    ],
)
def test_transicoes_invalidas(atual, acao, contrib):
    with pytest.raises(TransicaoInvalida):
        transicionar(atual, acao, tem_contribuicao=contrib)
