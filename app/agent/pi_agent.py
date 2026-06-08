from langchain.agents import create_agent

from app.agent.tools_registry import get_pims_tools
from app.prompts.pi_agent_prompt import AGENT_SYSTEM_PROMPT


def create_pi_agent(llm):
    return create_agent(
        model=llm,
        tools=get_pims_tools(),
        system_prompt=AGENT_SYSTEM_PROMPT,
    )


async def run_pi_agent(llm, user_message: str) -> dict:
    agent = create_pi_agent(llm)

    return await agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": user_message,
                }
            ]
        }
    )