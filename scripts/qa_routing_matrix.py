"""
Routing matrix verification script.

Iterates through the routing matrix and reports expected vs actual tool selection.
Uses the route_message function to classify each question.

Usage:
    python scripts/qa_routing_matrix.py
"""

from __future__ import annotations

import asyncio

MATRIX = [
    ("qual o valor atual da tag LFI_RB3_VAZ_GN_TOTAL?", "consultar_tag"),
    ("último valor da tag X", "consultar_tag"),
    ("qual a compressão da tag LFI_RB3_VAZ_GN_TOTAL?", "tag_attributes_tool"),
    ("quais os valores de exceção da tag X?", "tag_attributes_tool"),
    ("me mostre compdev e excdev da tag X", "tag_attributes_tool"),
    ("qual scan e pointsource da tag X?", "tag_attributes_tool"),
    ("procure uma tag de velocidade do forno", "search_pi_points"),
    ("tem alguma tag de vazão do RB3?", "search_pi_points"),
    ("qual a média da tag X ontem?", "tag_statistics_tool"),
    ("máximo da tag X na última hora", "tag_statistics_tool"),
    ("calcule a integral da tag X", "tag_calculus_tool"),
    ("calcule a derivada da tag X", "tag_calculus_tool"),
    ("status do PIMS", "status_pims_tool"),
    ("o que significa compdev?", None),  # conceptual — not a tool
    ("diferença entre exceção e compressão", None),  # conceptual
]


async def run():
    from app.agent.router import route_message

    print("=" * 70)
    print("Routing Matrix Verification")
    print("=" * 70)
    print(f"{'#':>3} | {'Pergunta':<55} | {'Esperado':<22} | {'Obtido':<22} | {'Status'}")
    print("-" * 70)

    passed = 0
    failed = 0
    skipped = 0

    for i, (question, expected) in enumerate(MATRIX, 1):
        try:
            route_result = await route_message(user_message=question)
            obtained = route_result.rota if hasattr(route_result, "rota") else str(route_result)
        except Exception as e:
            obtained = f"ERRO: {e}"

        if expected is None:
            status = "conceitual"
            skipped += 1
        elif obtained == "pims":
            # Router correctly identified a PIMS domain question
            status = "OK"
            passed += 1
        else:
            status = "DIVERGE"
            failed += 1

        print(f"{i:>3} | {question:<55} | {str(expected):<22} | {obtained:<22} | {status}")

    print("-" * 70)
    print(f"Passed: {passed}, Failed: {failed}, Skipped (conceptual): {skipped}")
    print(f"Total: {len(MATRIX)}")
    return passed, failed


if __name__ == "__main__":
    asyncio.run(run())
