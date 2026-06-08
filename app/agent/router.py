from typing import Literal

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, ConfigDict

from app.prompts.router_prompt import ROUTER_PROMPT


RouteName = Literal[
    "conversa_comum",
    "calculadora",
    "pims",
]


class RouterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rota: RouteName = Field(
        description=(
            "Rota escolhida para tratar a mensagem do usuário. "
            "Use somente: conversa_comum, calculadora ou pims."
        )
    )


def _fallback_route() -> RouterOutput:
    return RouterOutput(rota="conversa_comum")


async def route_message(llm, user_message: str) -> RouterOutput:
    parser = PydanticOutputParser(pydantic_object=RouterOutput)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", ROUTER_PROMPT),
            ("user", "Mensagem para classificar:\n{user_message}"),
        ]
    )

    chain = prompt | llm | parser

    try:
        route = await chain.ainvoke(
            {
                "user_message": user_message,
                "format_instructions": parser.get_format_instructions(),
            }
        )

        if not route or not route.rota:
            return _fallback_route()

        return route

    except Exception:
        return _fallback_route()