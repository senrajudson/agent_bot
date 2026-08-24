"""
Gate Ambiental V1-V9: Validação Read-Only da PI Web API para /streamsets/summary e /streams/{webId}/summary.
NENHUMA OPERAÇÃO DE ESCRITA É EXECUTADA (100% GET).
"""

import asyncio
import logging
import time
from typing import Any
import httpx

from mcp_server.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("validate_pi_summary_gate")


def _get_auth() -> tuple[str, str] | None:
    if settings.PI_WEB_API_USERNAME and settings.PI_WEB_API_PASSWORD:
        return settings.PI_WEB_API_USERNAME, settings.PI_WEB_API_PASSWORD
    return None


def _base_url() -> str:
    return settings.PI_WEB_API_BASE_URL.rstrip("/")


async def run_v1_to_v9_tests():
    auth = _get_auth()
    base = _base_url()
    
    async with httpx.AsyncClient(auth=auth, verify=settings.PI_WEB_API_VERIFY_SSL, timeout=30.0) as client:
        logger.info("=== Obter DataServers para listar tags reais ===")
        ds_resp = await client.get(f"{base}/dataservers")
        if ds_resp.status_code != 200:
            logger.error(f"Falha ao obter dataservers: HTTP {ds_resp.status_code}")
            return
        
        ds_items = ds_resp.json().get("Items", [])
        if not ds_items:
            logger.error("Nenhum DataServer encontrado.")
            return
        
        ds_webid = ds_items[0]["WebId"]
        logger.info(f"DataServer WebId: {ds_webid}")
        
        logger.info("=== Obter lista de PI Points ===")
        pts_resp = await client.get(f"{base}/dataservers/{ds_webid}/points", params={"maxCount": 50})
        if pts_resp.status_code != 200:
            logger.error(f"Falha ao obter points: HTTP {pts_resp.status_code}")
            return
        
        items = pts_resp.json().get("Items", [])
        web_ids = [item["WebId"] for item in items if "WebId" in item]
        logger.info(f"Obtidos {len(web_ids)} WebIds reais de PI Points.")

        if not web_ids:
            logger.warning("Nenhum WebId encontrado.")
            return

        # -------------------------------------------------------------------
        # V1: Teste de Lote de WebIds
        # -------------------------------------------------------------------
        logger.info("\n--- V1: Teste de Lote de WebIds (/streamsets/summary) ---")
        batch_sizes = [1, 5, 10, 25, 50]
        safe_batch_size = 1
        for size in batch_sizes:
            sub_ids = web_ids[:size]
            if len(sub_ids) < size:
                break
            
            params = [("webId", w) for w in sub_ids]
            params.append(("summaryType", "Average"))
            params.append(("startTime", "*-24h"))
            params.append(("endTime", "*"))
            
            t0 = time.monotonic()
            res = await client.get(f"{base}/streamsets/summary", params=params)
            elapsed = (time.monotonic() - t0) * 1000
            
            req_url_len = len(str(res.url))
            logger.info(
                f"Lote size={size}: HTTP {res.status_code} | "
                f"Elapsed={elapsed:.1f}ms | URLLen={req_url_len}"
            )
            if res.status_code == 200:
                safe_batch_size = size
                body = res.json()
                ret_items = body.get("Items", [])
                logger.info(f"  -> Retornados {len(ret_items)} itens.")

        logger.info(f"==> SUMMARY_BATCH_SIZE recomendado: {safe_batch_size}")

        # -------------------------------------------------------------------
        # V2: Múltiplos Summary Types na mesma chamada
        # -------------------------------------------------------------------
        logger.info("\n--- V2: Múltiplos Summary Types ---")
        sample_ids = web_ids[:2]
        params = [("webId", w) for w in sample_ids]
        summary_types = [
            "Average", "Minimum", "Maximum", "Count",
            "StdDev", "PopulationStdDev", "Range", "PercentGood"
        ]
        for st in summary_types:
            params.append(("summaryType", st))
        params.append(("startTime", "*-24h"))
        params.append(("endTime", "*"))

        res = await client.get(f"{base}/streamsets/summary", params=params)
        logger.info(f"V2 Multiple summaryTypes: HTTP {res.status_code}")
        if res.status_code == 200:
            body = res.json()
            items = body.get("Items", [])
            logger.info(f"  -> Itens retornados: {len(items)}")
            if items:
                summaries = items[0].get("Items", [])
                st_names = [s.get("Type") for s in summaries]
                logger.info(f"  -> Types encontrados no primeiro item: {st_names}")

        # -------------------------------------------------------------------
        # V3: summaryDuration (Buckets temporais)
        # -------------------------------------------------------------------
        logger.info("\n--- V3: summaryDuration (Buckets temporais) ---")
        durations = ["5m", "15m", "1h"]
        for dur in durations:
            params = [
                ("webId", web_ids[0]),
                ("summaryType", "Average"),
                ("startTime", "*-24h"),
                ("endTime", "*"),
                ("summaryDuration", dur),
            ]
            res = await client.get(f"{base}/streams/{web_ids[0]}/summary", params=params)
            logger.info(f"V3 duration={dur}: HTTP {res.status_code}")
            if res.status_code == 200:
                b_items = res.json().get("Items", [])
                logger.info(f"  -> Quantidade de buckets retornados para {dur}: {len(b_items)}")

        # -------------------------------------------------------------------
        # V4: Calculation Basis (TimeWeighted vs EventWeighted)
        # -------------------------------------------------------------------
        logger.info("\n--- V4: Calculation Basis ---")
        for basis in ["TimeWeighted", "EventWeighted"]:
            params = [
                ("webId", web_ids[0]),
                ("summaryType", "Average"),
                ("startTime", "*-24h"),
                ("endTime", "*"),
                ("calculationBasis", basis),
            ]
            res = await client.get(f"{base}/streams/{web_ids[0]}/summary", params=params)
            logger.info(f"V4 basis={basis}: HTTP {res.status_code}")
            if res.status_code == 200:
                b_items = res.json().get("Items", [])
                val = b_items[0].get("Value", {}).get("Value") if b_items else None
                logger.info(f"  -> Média com {basis}: {val}")


async def main():
    logger.info("Iniciando execução dos testes do Gate Ambiental V1-V9...")
    try:
        await run_v1_to_v9_tests()
    except Exception as exc:
        logger.error(f"Erro durante o gate: {exc}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
