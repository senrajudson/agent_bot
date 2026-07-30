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
| 20 | consumo minuto a minuto da tag X | `tag_statistics_tool` com `group_by="1m"`, `return_series=True` | Operacional |
| 21 | média da tag X por minuto | `tag_statistics_tool` com `group_by="1m"`, `return_series=True` | Operacional |
| 22 | consumo da tag X sem granularidade | `tag_statistics_tool` com `return_series=True` (group_by default 1h) | Operacional |
| 23 | média da tag X com group_by='5m' | Erro `INVALID_GROUP_BY` | Erro contratual |
| 24 | consumo da tag X com group_by='2h' | Erro `INVALID_GROUP_BY` | Erro contratual |
| 25 | gere um CSV com os valores da TAG minuto a minuto da hora anterior | `generate_pi_tags_series_csv` com `data_method=interpolated`, `interval=1m`, sem `operation` | Operacional |
| 26 | gere um CSV com os valores brutos da TAG na última hora | `generate_pi_tags_series_csv` com `data_method=recorded`, sem `interval` | Operacional |
| 27 | qual foi a média por minuto da TAG na última hora? | `tag_statistics_tool` com `operation=mean`, `data_method=summary`, `group_by=1m`, `summary_duration=1m` | Operacional |
| 28 | qual foi o máximo a cada cinco minutos? | `tag_statistics_tool` com `operation=max`, `data_method=summary`, `group_by=5m`, `summary_duration=5m` | Operacional |
| 29 | valores minuto a minuto | NÃO usar `operation=mean`, NÃO usar `tag_statistics_tool` | Regra negativa |
| 30 | velocidade rb2 | `search_pi_points`, deve conter `LFS_RB2_VELOPROC`, NÃO deve conter corrente RB2 nem RB3 | Multi-token AND |
| 31 | rb2 velocidade | `search_pi_points`, resultado equivalente ao caso 30 (independência de ordem) | Multi-token AND |
| 32 | velocidade rb3 | `search_pi_points`, NÃO deve conter RB2 | Multi-token AND |
| 33 | corrente rb2 | `search_pi_points`, NÃO deve conter velocidade nem RB3 | Multi-token AND |
| 34 | termo sem correspondência (ex.: "xyzabc") | `search_pi_points` → `no_confident_match`, `isError=false`, 0 resultados | no_confident_match |
| 35 | taxa de variação (termo inexistente) | `search_pi_points` → `no_confident_match`, `suggestions` com refinamento | no_confident_match |
| 36 | RB2 (termo único amplo) | `search_pi_points`, deve retornar top tags com RB2 no nome/descrição | Termo único |
