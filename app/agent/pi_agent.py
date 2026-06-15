from langchain.agents import create_agent

from app.agent.tools_registry import get_pims_tools
from app.prompts.pi_agent_prompt import AGENT_SYSTEM_PROMPT

MAX_AGENT_STEPS = 6


def create_pi_agent(llm):
    return create_agent(
        model=llm,
        tools=get_pims_tools(),
        system_prompt=AGENT_SYSTEM_PROMPT,
    )


async def run_pi_agent(llm, user_message: str) -> dict:
    agent = create_pi_agent(llm)

    try:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": user_message}]},
            config={"recursion_limit": MAX_AGENT_STEPS},
        )
    except Exception as e:
        error_msg = str(e)
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

        return {
            "messages": [
                type("Msg", (), {
                    "type": "ai",
                    "content": f"Não consegui executar a consulta. Erro: {error_msg}",
                    "tool_calls": None,
                    "name": None,
                })()
            ]
        }

    messages = result.get("messages", [])
    if not messages:
        return result

    tool_calls_seen = set()
    for msg in messages:
        tool_calls = getattr(msg, "tool_calls", None) or []
        for tc in tool_calls:
            tc_key = f"{tc.get('name', '')}:{tc.get('args', {})}"

            if tc_key in tool_calls_seen:
                return {
                    "messages": [
                        type("Msg", (), {
                            "type": "ai",
                            "content": (
                                "Não consegui concluir a consulta porque o agente "
                                "tentou repetir a mesma chamada de ferramenta. "
                                "A execução foi encerrada para evitar repetição."
                            ),
                            "tool_calls": None,
                            "name": None,
                        })()
                    ]
                }

            tool_calls_seen.add(tc_key)

    return result
