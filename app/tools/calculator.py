from langchain_core.tools import tool
from pydantic import BaseModel, Field, ConfigDict

from app.services.math_tool_service import executar_calculo_simples_service


class CalculatorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expression: str = Field(
        description=(
            "Expressão matemática simples já normalizada e pronta para cálculo. "
            "Use esta tool apenas para matemática pura, sem tags do PI System, sem PIMS, "
            "sem PI Web API e sem dados reais da usina. "
            "Exemplos válidos: '300 / 2', '0.15 * 200', '10 + 20 * 3', '1758 * 0.30'. "
            "Para porcentagem, o agente deve converter antes de chamar a tool. "
            "Exemplo: '30% de 1758' deve ser enviado como '0.30 * 1758'. "
            "Não envie texto natural dentro de expression. "
            "Não use esta tool para média, máximo, mínimo, soma histórica, consumo, "
            "histórico de tag, integralização, derivada ou status operacional."
        )
    )

    pergunta_usuario: str | None = Field(
        default=None,
        description=(
            "Pergunta original do usuário. "
            "Preencha sempre que possível para rastreabilidade. "
            "Não use este campo para cálculo; o cálculo deve estar somente em expression."
        ),
    )


@tool(args_schema=CalculatorInput)
async def calculator_tool(
    expression: str,
    pergunta_usuario: str | None = None,
) -> str:
    """
    Executa cálculos matemáticos simples que não envolvem tags do PI System.

    Use esta tool quando o usuário pedir matemática pura, como:
    - porcentagem;
    - divisão;
    - multiplicação;
    - soma;
    - subtração;
    - regra de três simples;
    - expressões aritméticas simples.

    Contrato:
    - Sempre envie todos os campos do schema.
    - expression deve conter apenas a expressão matemática pronta para cálculo.
    - pergunta_usuario deve conter a pergunta original do usuário, quando disponível.
    - Não envie campos fora do schema.
    - A tool não normaliza texto automaticamente.
    - A tool não converte porcentagem automaticamente.
    - A tool não detecta tags automaticamente.
    - O agente deve decidir se a solicitação é matemática pura antes de chamar esta tool.

    Exemplo - porcentagem:
    Usuário: "Quanto é 30% de 1758?"
    Use:
    calculator_tool({
        "expression": "0.30 * 1758",
        "pergunta_usuario": "Quanto é 30% de 1758?"
    })

    Exemplo - expressão aritmética:
    Usuário: "Calcule 10 + 20 vezes 3."
    Use:
    calculator_tool({
        "expression": "10 + 20 * 3",
        "pergunta_usuario": "Calcule 10 + 20 vezes 3."
    })

    Regras reforçadas pelos exemplos:
    - Use calculator_tool somente para matemática pura.
    - O agente deve transformar porcentagens em expressão numérica antes da chamada.
    - O agente deve evitar esta tool quando houver tag, PIMS, histórico, consumo, integral ou derivada.
    """

    result = await executar_calculo_simples_service(
        expression=expression,
    )

    return result["output"]