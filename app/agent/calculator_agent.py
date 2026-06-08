# from langchain.agents import create_agent

# from app.agent.tools_registry import get_calculator_tools
# from app.prompts.calculator_agent_prompt import CALCULATOR_AGENT_PROMPT


# def create_calculator_agent(llm):
#     return create_agent(
#         model=llm,
#         tools=get_calculator_tools(),
#         system_prompt=CALCULATOR_AGENT_PROMPT,
#     )


# async def run_calculator_agent(llm, user_message: str) -> dict:
#     agent = create_calculator_agent(llm)

#     return await agent.ainvoke(
#         {
#             "messages": [
#                 {
#                     "role": "user",
#                     "content": user_message,
#                 }
#             ]
#         }
#     )