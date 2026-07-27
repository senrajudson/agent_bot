import threading

from domain.core.integration_settings import DomainIntegrationSettings


_DOMAIN_CONFIG: DomainIntegrationSettings | None = None
_LOCK = threading.Lock()


def configure_domain_settings(settings: DomainIntegrationSettings) -> None:
    global _DOMAIN_CONFIG
    with _LOCK:
        if _DOMAIN_CONFIG is not None:
            raise RuntimeError(
                "DomainIntegrationSettings já foi configurado. "
                "configure_domain_settings() deve ser chamado uma única vez."
            )
        _DOMAIN_CONFIG = settings


def get_domain_settings() -> DomainIntegrationSettings:
    cfg = _DOMAIN_CONFIG
    if cfg is None:
        raise RuntimeError(
            "DomainIntegrationSettings não foi configurado. "
            "Chame configure_domain_settings() antes de acessar "
            "get_domain_settings()."
        )
    return cfg


def _reset_domain_settings(*, test_only: bool = False) -> None:
    if not test_only:
        raise RuntimeError(
            "_reset_domain_settings é permitido apenas em testes. "
            "Use test_only=True."
        )
    global _DOMAIN_CONFIG
    _DOMAIN_CONFIG = None
