"""
Limpa entradas poluídas da memória do Redis.
Critérios de poluição:
  - Conteúdo do assistant com 'parts=[Part(' (formato cru do ADK)
  - Conteúdo com '1050431' (valor fabricado conhecido)
  - Conteúdo com "Não consegui executar a consulta. Erro (ExceptionGroup)"
    (respostas de falha antiga quando MCP estava inacessível)
"""

import redis

REDIS_URL = "redis://10.247.179.197:6379/2"
POLLUTION_PATTERNS = [
    b"parts=[Part(",
    b"1050431",
    b"unhandled errors in a TaskGroup",
]


def main():
    r = redis.Redis.from_url(REDIS_URL, decode_responses=False)

    keys = [k.decode() for k in r.keys("pi_chat:memory:*") if b"turns" in k]
    print(f"Found {len(keys)} memory keys")

    total_removed = 0
    keys_cleared = 0

    for key in keys:
        items = r.lrange(key, 0, -1)
        if not items:
            continue

        polluted_indexes = []
        for i, item in enumerate(items):
            if any(pat in item for pat in POLLUTION_PATTERNS):
                polluted_indexes.append(i)

        if not polluted_indexes:
            continue

        print(f"\n=== {key} ===")
        print(f"  Total items: {len(items)}, polluted: {len(polluted_indexes)}")

        for idx in polluted_indexes:
            item = items[idx]
            snippet = item.decode()[:120].replace("\n", " ")
            print(f"  - idx {idx}: {snippet}...")

        keep = [it for i, it in enumerate(items) if i not in polluted_indexes]
        if keep:
            pipe = r.pipeline()
            pipe.delete(key)
            pipe.rpush(key, *keep)
            pipe.execute()
        else:
            r.delete(key)
            keys_cleared += 1

        total_removed += len(polluted_indexes)
        print(f"  -> removed {len(polluted_indexes)}, kept {len(keep)}")

    print(f"\n=== Summary ===")
    print(f"Total polluted entries removed: {total_removed}")
    print(f"Keys fully cleared (all entries were polluted): {keys_cleared}")


if __name__ == "__main__":
    main()
