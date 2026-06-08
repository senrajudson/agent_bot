# app/utils/google_chat_format.py

import re


def normalize_google_chat_markdown(text: str | None) -> str:
    if not text:
        return ""

    output = str(text)

    # Remove escape de underscore criado pelo modelo
    # Exemplo: CPD\_LP\_SECADOR\_STATUS -> CPD_LP_SECADOR_STATUS
    output = output.replace(r"\_", "_")

    # Troca qualquer sequência de 2 ou mais asteriscos por apenas 1
    # Exemplo: **texto** -> *texto*
    # Exemplo: ***texto*** -> *texto*
    output = re.sub(r"\*{2,}", "*", output)

    return output.strip()