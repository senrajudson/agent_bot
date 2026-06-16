from langchain.agents import create_agent

from app.prompts.general_agent_prompt import GENERAL_AGENT_PROMPT


def create_general_agent(llm):
    return create_agent(
        model=llm,
        tools=[],
        system_prompt=GENERAL_AGENT_PROMPT,
    )


async def run_general_agent(llm, user_message: str) -> dict:
    agent = create_general_agent(llm)

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