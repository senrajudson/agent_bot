# Matriz de Roteamento — MCP Tools

> Gerada para validar a hierarquia MCP → Services → RAG.
> Perguntas operacionais devem funcionar sem RAG (CHUNK 01 é suficiente).
> Perguntas conceituais podem depender do RAG.

| # | Pergunta | Caminho esperado | Tipo |
|---|----------|-----------------|------|
| 1 | qual o valor atual da tag X? | `consultar_tag` | Operacional |
| 2 | último valor da tag X | `consultar_tag` | Operacional |
| 3 | qual a compressão da tag X? | `tag_attributes_tool` | Operacional |
| 4 | quais os valores de exceção da tag X? | `tag_attributes_tool` | Operacional |
| 5 | me mostre compdev e excdev da tag X | `tag_attributes_tool` | Operacional |
| 6 | qual scan e pointsource da tag X? | `tag_attributes_tool` | Operacional |
| 7 | procure uma tag de velocidade do forno | `search_pi_points` | Operacional |
| 8 | tem alguma tag de vazão do RB3? | `search_pi_points` | Operacional |
| 9 | qual a média da tag X ontem? | `tag_statistics_tool` | Operacional |
| 10 | máximo da tag X na última hora | `tag_statistics_tool` | Operacional |
| 11 | calcule a integral da tag X | `tag_calculus_tool` | Operacional |
| 12 | calcule a derivada da tag X | `tag_calculus_tool` | Operacional |
| 13 | status do PIMS | `status_pims_tool` | Operacional |
| 14 | o que significa compdev? | RAG/conceitual | Conceitual |
| 15 | diferença entre exceção e compressão | RAG/conceitual | Conceitual |
| 16 | 1ª search_pi_points retorna vazio, 2ª com query diferente retorna candidatos | 2 search_pi_points, resposta com candidatos | Política |
| 17 | 3 chamadas consecutivas de search_pi_points | 2 search_pi_points, resposta com melhor resultado da 1ª ou 2ª, 3ª suprimida | Política |
| 18 | consumo de cada dia da semana passada da tag X | `tag_statistics_tool` com `group_by="1d"`, `return_series=True` | Operacional |
| 19 | consumo mês a mês da tag X neste ano | `tag_statistics_tool` com `group_by="1mo"`, `return_series=True` | Operacional |
