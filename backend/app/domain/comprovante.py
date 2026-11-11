"""Conferência do texto de um comprovante PIX (extraído por OCR ou do PDF).

Função pura: recebe o texto e o que se espera dele, devolve o que bate e o que não bate.
Não usa IA — só padrões que todo comprovante brasileiro tem (R$ 0,00, datas, nomes, ID E2E).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

MESES = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}  # fmt: skip

# Palavras que não identificam ninguém (não contam no casamento de nomes)
IGNORAR_NOME = {"de", "da", "do", "das", "dos", "e", "ltda", "me", "sa", "s/a"}

# ID fim-a-fim do PIX: E + ISPB(8) + data/hora(12) + 11 alfanuméricos = 32 caracteres
RE_E2E = re.compile(r"\bE\d{8}\d{12}[A-Za-z0-9]{11}\b")
RE_VALOR_RS = re.compile(r"R\s*\$\s*([\d.\s]*\d,\d{2})")
RE_VALOR_SOLTO = re.compile(r"(?<![\d,.])(\d{1,3}(?:\.\d{3})*,\d{2})(?![\d,])")
RE_DATA_NUM = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b")
RE_DATA_EXT = re.compile(
    r"\b(\d{1,2})\s*(?:de\s+)?(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[a-zç]*\.?"
    r"\s*(?:de\s+)?(\d{4})\b",
    re.IGNORECASE,
)


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento, espaços simples. Corrige confusões comuns do OCR (0/O em nomes)."""
    sem = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem.lower()).strip()


def _palavras(texto: str) -> list[str]:
    return re.findall(r"[a-z]+", normalizar(texto))


# ---------------------------------------------------------------------------
# Extração
# ---------------------------------------------------------------------------
def extrair_valores(texto: str) -> list[Decimal]:
    """Valores em reais. Prioriza os que vêm com 'R$'; se não houver, aceita '30,00' solto."""
    achados = RE_VALOR_RS.findall(texto) or RE_VALOR_SOLTO.findall(texto)
    valores: list[Decimal] = []
    for bruto in achados:
        limpo = re.sub(r"[\s.]", "", bruto).replace(",", ".")
        try:
            v = Decimal(limpo)
        except InvalidOperation:
            continue
        if v > 0 and v not in valores:
            valores.append(v)
    return valores


def extrair_datas(texto: str) -> list[date]:
    datas: list[date] = []

    def add(d: int, m: int, a: int) -> None:
        if a < 100:
            a += 2000
        try:
            dt = date(a, m, d)
        except ValueError:
            return
        if dt not in datas:
            datas.append(dt)

    for d, m, a in RE_DATA_NUM.findall(texto):
        add(int(d), int(m), int(a))
    for d, mes, a in RE_DATA_EXT.findall(normalizar(texto)):
        add(int(d), MESES[mes[:3].lower()], int(a))
    return datas


def extrair_e2e(texto: str) -> str | None:
    m = RE_E2E.search(texto.replace(" ", ""))
    return m.group(0) if m else None


def nome_aparece(nome: str, texto: str) -> bool:
    """O nome 'aparece' se o primeiro nome e ao menos mais um pedaço estão no texto.

    Nome de uma palavra só: basta ela. Tolera abreviação (ex.: 'Isac C Alves').
    """
    partes = [p for p in _palavras(nome) if p not in IGNORAR_NOME and len(p) > 1]
    if not partes:
        return False
    palavras = set(_palavras(texto))
    if partes[0] not in palavras:
        return False
    if len(partes) == 1:
        return True
    resto = partes[1:]
    return any(p in palavras for p in resto) or any(
        p[0] in palavras
        for p in resto  # sobrenome abreviado: "C"
    )


# ---------------------------------------------------------------------------
# Conferência
# ---------------------------------------------------------------------------
@dataclass
class Analise:
    valor_confere: bool
    data_confere: bool
    recebedor_confere: bool | None  # None = organizador não informou o nome
    convidado_confere: bool
    repetido: bool
    valores_encontrados: list[str] = field(default_factory=list)
    datas_encontradas: list[str] = field(default_factory=list)
    e2e: str | None = None
    texto_legivel: bool = True

    @property
    def tudo_confere(self) -> bool:
        """Critério da baixa automática: valor, data e recebedor batem e não é repetido.

        O nome do convidado não bloqueia (outra pessoa pode ter pago por ele).
        """
        return (
            self.texto_legivel
            and self.valor_confere
            and self.data_confere
            and self.recebedor_confere is not False
            and not self.repetido
        )

    def para_json(self) -> dict:
        d = asdict(self)
        d["tudo_confere"] = self.tudo_confere
        return d


def analisar(
    texto: str | None,
    *,
    valor_esperado: Decimal,
    nome_convidado: str,
    nome_recebedor: str | None,
    desde: date,
    hoje: date,
    e2e_ja_usados: set[str] | None = None,
) -> Analise:
    if not texto or len(normalizar(texto)) < 15:
        return Analise(False, False, None, False, False, texto_legivel=False)

    valores = extrair_valores(texto)
    datas = extrair_datas(texto)
    e2e = extrair_e2e(texto)
    return Analise(
        valor_confere=valor_esperado.quantize(Decimal("0.01")) in valores,
        data_confere=any(desde <= d <= hoje for d in datas),
        recebedor_confere=nome_aparece(nome_recebedor, texto) if nome_recebedor else None,
        convidado_confere=nome_aparece(nome_convidado, texto),
        repetido=bool(e2e and e2e in (e2e_ja_usados or set())),
        valores_encontrados=[f"{v:.2f}" for v in valores],
        datas_encontradas=[d.isoformat() for d in datas],
        e2e=e2e,
    )
