import sys
from pathlib import Path

from langchain.agents import create_agent

from app.core.config import settings
from app.prompts.pi_agent_prompt import AGENT_SYSTEM_PROMPT


sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mcp_server"))

MAX_AGENT_STEPS = 6
MCP_SERVER_URL = settings.MCP_SERVER_URL

async def _run_with_mcp(llm, user_message: str) -> dict:
    """
    Run the agent with a persistent MCP connection.
    The MCP session must stay open while the agent is running.
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from langchain_mcp_adapters.tools import load_mcp_tools

    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)

            agent = create_agent(
                model=llm,
                tools=tools,
                system_prompt=AGENT_SYSTEM_PROMPT,
            )

            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": user_message}]},
                config={"recursion_limit": MAX_AGENT_STEPS},
            )
            return result


async def run_pi_agent(llm, user_message: str) -> dict:
    try:
        result = await _run_with_mcp(llm, user_message)
    except Exception as e:
        import traceback
        error_msg = str(e) or type(e).__name__
        error_type = type(e).__name__

        if "RecursionError" in error_type or "recursion_limit" in error_msg:
            return {
                "messages": [
                    type("Msg", (), {
                        "type": "ai",
                        "content": (
                            "Não consegui concluir a consulta porque o agente "
                            "excedeu o número máximo de etapas permitidas. "
                            "Tente reformular a pergunta com mais detalhes."
                        ),
                        "tool_calls": None,
                        "name": None,
                    })()
                ]
            }

        if "RateLimitError" in error_type or "rate_limit" in error_msg or "429" in error_msg:
            return {
                "messages": [
                    type("Msg", (), {
                        "type": "ai",
                        "content": "Serviço temporariamente sobrecarregado. Tente novamente em instantes.",
                        "tool_calls": None,
                        "name": None,
                    })()
                ]
            }

        if "AuthenticationError" in error_type or "401" in error_msg:
            return {
                "messages": [
                    type("Msg", (), {
                        "type": "ai",
                        "content": "Chave de API do modelo LLM inválida ou expirada. Verifique a configuração.",
                        "tool_calls": None,
                        "name": None,
                    })()
                ]
            }

        if "ClosedResourceError" in error_type:
            return {
                "messages": [
                    type("Msg", (), {
                        "type": "ai",
                        "content": "Conexão com o servidor de ferramentas foi fechada. Tente novamente.",
                        "tool_calls": None,
                        "name": None,
                    })()
                ]
            }

        return {
            "messages": [
                type("Msg", (), {
                    "type": "ai",
                    "content": f"Não consegui executar a consulta. Erro ({error_type}): {error_msg}",
                    "tool_calls": None,
                    "name": None,
                })()
            ]
        }

    messages = result.get("messages", [])
    if not messages:
        return result

    tool_call_counts = {}
    for msg in messages:
        tool_calls = getattr(msg, "tool_calls", None) or []
        for tc in tool_calls:
            tc_key = f"{tc.get('name', '')}:{tc.get('args', {})}"
            tool_call_counts[tc_key] = tool_call_counts.get(tc_key, 0) + 1

            if tool_call_counts[tc_key] >= 3:
                return {
                    "messages": [
                        type("Msg", (), {
                            "type": "ai",
                            "content": (
                                "Não consegui concluir a consulta porque o agente "
                                "tentou repetir a mesma chamada de ferramenta "
                                "múltiplas vezes. A execução foi encerrada para evitar repetição."
                            ),
                            "tool_calls": None,
                            "name": None,
                        })()
                    ]
                }

    return result
