from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Capacidade máxima segura de linhas para arquivo XLSX (Excel suporta até 1.048.576)
EXCEL_SAFE_ROW_LIMIT = 1_000_000
PI_REQUEST_SAFE_LIMIT = 150_000
DEFAULT_CONFIGURED_LIMIT = 150_000


@dataclass(frozen=True)
class EffectiveLimitResolution:
    configured_limit: int
    pi_request_safe_limit: int
    artifact_safe_row_limit: int
    effective_limit: int
    clamped: bool
    clamp_warning: Optional[str] = None


def resolve_effective_point_limit(
    configured_limit: int = DEFAULT_CONFIGURED_LIMIT,
    pi_safe_limit: int = PI_REQUEST_SAFE_LIMIT,
    excel_safe_limit: int = EXCEL_SAFE_ROW_LIMIT,
) -> EffectiveLimitResolution:
    """Calcula effective_point_limit = min(configured, pi_safe, excel_safe).

    Aplica clamp com warning explícito caso o limite configurado exceda a capacidade da planilha.
    """
    if configured_limit <= 0:
        raise ValueError(f"Limite de pontos configurado inválido: {configured_limit}. Deve ser > 0.")

    effective = min(configured_limit, pi_safe_limit, excel_safe_limit)
    clamped = False
    clamp_warning = None

    if configured_limit > excel_safe_limit:
        clamped = True
        clamp_warning = (
            f"[POINT_LIMIT_REDUCED_TO_ARTIFACT_CAPACITY] Limite configurado ({configured_limit}) "
            f"excede a capacidade segura do artefato XLSX ({excel_safe_limit}). "
            f"O limite efetivo foi reduzido para {effective}."
        )
        logger.warning(clamp_warning)

    return EffectiveLimitResolution(
        configured_limit=configured_limit,
        pi_request_safe_limit=pi_safe_limit,
        artifact_safe_row_limit=excel_safe_limit,
        effective_limit=effective,
        clamped=clamped,
        clamp_warning=clamp_warning,
    )
