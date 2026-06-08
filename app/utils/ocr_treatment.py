import re
from pydantic import BaseModel


TAG_REGEX = re.compile(
    r"\b(?:UTI|ACI|RED|LFS|LFI|CPD|LTQ)(?:_[A-Z0-9]+)+\b"
    r"|\b(?:SIN|CDT)[A-Z0-9_]+\b"
)


class OcrTreatmentResult(BaseModel):
    texto_ocr_original: str
    texto_ocr_normalizado: str
    tags_encontradas: list[str]
    resultado: str


def eh_inicio_tag_completa(linha: str = "") -> bool:
    return bool(
        re.match(r"^(?:UTI|ACI|RED|LFS|LFI|CPD|LTQ)(?:_[A-Z0-9]+)+$", linha)
        or re.match(r"^(?:SIN|CDT)[A-Z0-9_]+$", linha)
    )


def eh_inicio_tag_ou_prefixo(linha: str = "") -> bool:
    return bool(
        re.match(r"^(?:UTI|ACI|RED|LFS|LFI|CPD|LTQ)(?:_[A-Z0-9]+)+$", linha)
        or re.match(r"^(?:SIN|CDT)[A-Z0-9_]+$", linha)
        or re.match(r"^(?:UTI|ACI|RED|LFS|LFI|CPD|LTQ)(?:_[A-Z0-9]+)*$", linha)
        or re.match(r"^(?:SIN|CDT)[A-Z0-9_]*$", linha)
    )


def eh_fragmento_continuacao(linha: str = "") -> bool:
    return bool(re.match(r"^_?[A-Z0-9]+(?:_[A-Z0-9]+)*$", linha))


def normalizar_texto_ocr(texto: str = "") -> str:
    texto_tratado = texto.replace("\r", "").replace("\\n", "\n")

    linhas = [linha.strip() for linha in texto_tratado.split("\n")]

    resultado: list[str] = []
    i = 0

    while i < len(linhas):
        atual = linhas[i]

        if not atual:
            i += 1
            continue

        if re.match(r"^nome da tag$", atual, re.IGNORECASE):
            resultado.append(atual)
            i += 1
            continue

        if eh_inicio_tag_ou_prefixo(atual):
            acumulado = atual
            j = i + 1

            while j < len(linhas):
                prox = linhas[j]

                if not prox:
                    break

                if eh_inicio_tag_completa(prox):
                    break

                if eh_fragmento_continuacao(prox):
                    acumulado += prox
                    j += 1
                    continue

                break

            resultado.append(acumulado)
            i = j
            continue

        resultado.append(atual)
        i += 1

    return "\n".join(resultado)


def extrair_tags(texto: str = "") -> list[str]:
    tags = TAG_REGEX.findall(texto)

    tags_unicas = []
    vistos = set()

    for tag in tags:
        if tag not in vistos:
            tags_unicas.append(tag)
            vistos.add(tag)

    return tags_unicas


def tratar_saida_ocr(texto_ocr_original: str = "") -> OcrTreatmentResult:
    texto_original = texto_ocr_original.strip()

    if not texto_original:
        texto_original = "[Nenhum texto encontrado]"

    texto_normalizado = normalizar_texto_ocr(texto_original).strip()
    tags_encontradas = extrair_tags(texto_normalizado)

    resultado = (
        "\n".join(tags_encontradas)
        if tags_encontradas
        else texto_normalizado
    )

    return OcrTreatmentResult(
        texto_ocr_original=texto_original,
        texto_ocr_normalizado=texto_normalizado,
        tags_encontradas=tags_encontradas,
        resultado=resultado.strip(),
    )