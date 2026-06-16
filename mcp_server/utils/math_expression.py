import re
import unicodedata


def remover_acentos(texto: str) -> str:
    return (
        unicodedata.normalize("NFD", str(texto or ""))
        .encode("ascii", "ignore")
        .decode("utf-8")
    )


def limpar_expressao_basica(texto: str) -> str:
    expr = remover_acentos(texto).lower()

    expr = (
        expr.replace("quanto e", "")
        .replace("calcule", "")
        .replace("calcular", "")
        .replace("resolva", "")
        .replace("resolver", "")
        .replace("conta", "")
        .replace("?", "")
        .strip()
    )

    percentual_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*%\s*(?:de|do|da)?\s*(\d+(?:[.,]\d+)?)",
        expr,
    )

    if percentual_match:
        percentual = float(percentual_match.group(1).replace(",", ".")) / 100
        valor = float(percentual_match.group(2).replace(",", "."))
        return f"{percentual} * {valor}"

    expr = (
        expr.replace("vezes", "*")
        .replace("multiplicado por", "*")
        .replace("dividido por", "/")
        .replace("mais", "+")
        .replace("menos", "-")
        .replace(",", ".")
    )

    expr = re.sub(r"[^0-9+\-*/().\s^]", "", expr).strip()

    if not expr:
        raise ValueError("Não foi possível extrair uma expressão aritmética válida.")

    return expr