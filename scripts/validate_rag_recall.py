#!/usr/bin/env python3
"""
Validate RAG recall and latency across Qdrant collections.

Loads annotated questions from a JSON fixture, queries each collection
via retrieve_relevant_chunks, and reports recall@1, recall@3, and
p50/p95 latency.

Usage:
    poetry run python scripts/validate_rag_recall.py \
        --questions tests/fixtures/rag_validation_questions.json \
        --collections pi_web_api_guide pi_web_api_guide_gemini2_768_v1 \
        --output reports/rag_validation.md
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.clients.qdrant_client import retrieve_relevant_chunks


def load_questions(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) > 0, "Questions file is empty"
    for q in data:
        assert "query" in q, f"Missing 'query' in question {q.get('id')}"
        assert "expected_top1" in q, f"Missing 'expected_top1' in question {q.get('id')}"
    return data


def validate_collection(
    questions: list[dict],
    collection: str,
    top_k: int = 3,
) -> dict:
    correct_top1 = 0
    correct_top3 = 0
    latencies: list[float] = []

    for q in questions:
        expected = q["expected_top1"]
        acceptable = set(q.get("expected_top3_acceptable", [expected]))

        start = time.perf_counter()
        results = retrieve_relevant_chunks(q["query"], top_k=top_k)
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)

        retrieved_numbers = [r["chunk_number"] for r in results]

        if retrieved_numbers and retrieved_numbers[0] == expected:
            correct_top1 += 1

        if expected in retrieved_numbers:
            correct_top3 += 1
        elif any(a in retrieved_numbers for a in acceptable):
            correct_top3 += 1

    n = len(questions)
    sorted_lat = sorted(latencies)
    p50 = sorted_lat[len(sorted_lat) // 2]
    p95 = sorted_lat[int(len(sorted_lat) * 0.95)]

    return {
        "collection": collection,
        "total": n,
        "recall_top1": correct_top1 / n,
        "recall_top3": correct_top3 / n,
        "correct_top1": correct_top1,
        "correct_top3": correct_top3,
        "latency_p50": round(p50, 4),
        "latency_p95": round(p95, 4),
    }


def build_report(results: list[dict], threshold_recall: float = 0.80) -> str:
    lines = [
        "# Validação de Recall e Latência — RAG Embeddings",
        "",
        f"| Coleção | Total | Recall@1 | Recall@3 | p50 (s) | p95 (s) |",
        f"|---------|-------|----------|----------|---------|---------|",
    ]

    for r in results:
        lines.append(
            f"| {r['collection']} | {r['total']} "
            f"| {r['recall_top1']:.0%} ({r['correct_top1']}/{r['total']}) "
            f"| {r['recall_top3']:.0%} ({r['correct_top3']}/{r['total']}) "
            f"| {r['latency_p50']:.3f} "
            f"| {r['latency_p95']:.3f} |"
        )

    lines.append("")

    if len(results) >= 2:
        gemini = results[-1]
        nomic = results[0]
        ratio = gemini["latency_p95"] / nomic["latency_p95"] if nomic["latency_p95"] > 0 else 999

        lines.append(f"### Veredito Recall@1")
        lines.append(f"")
        lines.append(f"Gemini Recall@1: {gemini['recall_top1']:.0%}")
        lines.append(f"CRITÉRIO CA8: ≥ {threshold_recall:.0%}")
        if gemini["recall_top1"] >= threshold_recall:
            lines.append(f"Resultado: ✅ PASS (RECALL OK)")
        else:
            lines.append(f"Resultado: ❌ FAIL (RECALL ABAIXO DO LIMIAR)")

        lines.append(f"")
        lines.append(f"### Veredito Latência")
        lines.append(f"")
        lines.append(f"Nomic p95: {nomic['latency_p95']:.3f}s")
        lines.append(f"Gemini p95: {gemini['latency_p95']:.3f}s")
        lines.append(f"Razão Gemini/Nomic: {ratio:.2f}x")
        lines.append(f"CRITÉRIO CA9: ≤ 1.50x")
        if ratio <= 1.50:
            lines.append(f"Resultado: ✅ PASS (LATÊNCIA OK)")
        else:
            lines.append(f"Resultado: ❌ FAIL (LATÊNCIA ACIMA DO LIMIAR)")

        recall_ok = gemini["recall_top1"] >= threshold_recall
        latency_ok = ratio <= 1.50
        lines.append(f"")
        lines.append(f"### Veredito Final")
        if recall_ok and latency_ok:
            lines.append(f"✅ **TODOS OS CRITÉRIOS ATENDIDOS — CUTOVER AUTORIZADO**")
        else:
            lines.append(f"❌ **CRITÉRIOS NÃO ATENDIDOS — CUTOVER BLOQUEADO**")
            if not recall_ok:
                lines.append(f"- Recall@1 abaixo do limiar ({gemini['recall_top1']:.0%} < {threshold_recall:.0%})")
            if not latency_ok:
                lines.append(f"- Latência Gemini {ratio:.2f}x acima do Nomic (limiar: 1.50x)")

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Validate RAG recall and latency across Qdrant collections."
    )
    parser.add_argument(
        "--questions", required=True,
        help="Path to JSON fixture with annotated questions",
    )
    parser.add_argument(
        "--collections", nargs="+", required=True,
        help="Collection names to validate (e.g. pi_web_api_guide pi_web_api_guide_gemini2_768_v1)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Path to write markdown report (default: print to stdout)",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.80,
        help="Minimum recall@1 threshold (default: 0.80)",
    )
    args = parser.parse_args()

    questions = load_questions(args.questions)
    print(f"Loaded {len(questions)} annotated questions from {args.questions}")

    # Stub: patch COLLECTION per query
    import app.clients.qdrant_client as qc

    results = []
    for collection in args.collections:
        print(f"\nValidating collection: {collection}")
        original = qc.COLLECTION
        qc.COLLECTION = collection

        try:
            result = validate_collection(questions, collection)
            results.append(result)
            print(f"  Recall@1: {result['recall_top1']:.0%} ({result['correct_top1']}/{result['total']})")
            print(f"  Recall@3: {result['recall_top3']:.0%} ({result['correct_top3']}/{result['total']})")
            print(f"  p50: {result['latency_p50']:.3f}s, p95: {result['latency_p95']:.3f}s")
        finally:
            qc.COLLECTION = original

    report = build_report(results, threshold_recall=args.threshold)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"\nReport written to {args.output}")
    else:
        print(f"\n{report}")

    # Exit code: 0 = all criteria met, 1 = any criteria failed
    if len(results) >= 2:
        gemini = results[-1]
        nomic = results[0]
        ratio = gemini["latency_p95"] / nomic["latency_p95"] if nomic["latency_p95"] > 0 else 999
        recall_ok = gemini["recall_top1"] >= args.threshold
        latency_ok = ratio <= 1.50
        sys.exit(0 if recall_ok and latency_ok else 1)


if __name__ == "__main__":
    main()
