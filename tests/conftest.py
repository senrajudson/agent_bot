"""Shared fixtures for agent_bot tests."""

import os

import textwrap

import pytest



SAMPLE_MARKDOWN = textwrap.dedent("""\
    # CHUNK 01 - Chunk fixo: selecao de tool e resumo operacional

    ## Mapa de tools

    | Intencao                           | Tool sugerida        |
    | ---------------------------------- | -------------------- |
    | Valor atual, metadados             | consultar_tag        |
    | Media, maximo, minimo, soma        | tag_statistics_tool  |
    | Integral, derivada                 | tag_calculus_tool    |
    | Status do PIMS                     | status_pims_tool     |

    ---

    # CHUNK 02 - Fluxo base: tag para WebId

    ## Fluxo essencial

    1. Montar path: \\\\PIMS\\NOME_DA_TAG
    2. Buscar PI Point: GET /points?path=\\\\PIMS\\NOME_DA_TAG
    3. Extrair WebId.

    GET http://10.247.224.39/piwebapi/points?path=\\\\PIMS\\LFI_RB3_VAZ_GN_TOTAL

    ---

    # CHUNK 03 - Valor atual de uma tag

    GET http://10.247.224.39/piwebapi/streams/{webId}/value

    ---

    # CHUNK 04 - Metadados da tag

    GET http://10.247.224.39/piwebapi/points?path=\\\\PIMS\\NOME_DA_TAG

    ---

    # CHUNK 20 - Calculos temporais: integral e derivada

    ## Integral

    tag_calculus_tool: operation="integral"

    ---

    # CHUNK 21 - RAG e recuperacao recomendada

    ## Recomendacao

    Use top-3 chunks retrieved.
""")


@pytest.fixture
def sample_markdown(tmp_path):
    """Write sample markdown to a temp file and return the path."""
    md_path = tmp_path / "PI_WEB_API_AGENT_GUIDE.md"
    md_path.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    return md_path
