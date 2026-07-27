from pydantic import BaseModel, ConfigDict, Field


class DomainIntegrationSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    PI_WEB_API_BASE_URL: str = Field(default="http://10.247.224.39/piwebapi")
    PI_SERVER_NAME: str = Field(default="PIMS")
    PI_WEB_API_USERNAME: str | None = None
    PI_WEB_API_PASSWORD: str | None = Field(default=None, repr=False)
    PI_WEB_API_VERIFY_SSL: bool = False

    MATH_TOOL_BASE_URL: str = Field(default="http://math_tool:8001")
    MATH_TOOL_TIMEOUT_SECONDS: float = 120.0

    GRAFANA_LOKI_QUERY_RANGE_URL: str = ""
    GRAFANA_BEARER_TOKEN: str = Field(default="", repr=False)

    PIMS_STATUS_LOKI_QUERY: str = Field(default='{job="zabbix_proxy"}')
    PIMS_STATUS_LOOKBACK_MINUTES: int = 20
    PIMS_STATUS_LIMIT: int = 5000

    REDIS_URL: str = Field(default="redis://127.0.0.1:6379/2")
