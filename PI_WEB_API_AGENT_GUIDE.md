# CHUNK 01 - Chunk fixo: seleção de tool e resumo operacional

## Intenção

Use como contexto base para orientar seleção de ferramenta e parâmetros.

## Política de entrega de resultados

Séries temporais, logs completos, timelines e relatórios multi-tag podem ser
entregues como um arquivo no Google Drive. Nesses casos, o retorno da tool MCP
será um manifesto compacto (`ArtifactManifest`) contendo status, metadados e o
link de visualização. Os dados brutos (linhas, buckets, pontos) não
são retornados ao modelo.

Quando receber `delivery: drive_artifact`:
- apresente `view_url` ao usuário;
- não chame a tool novamente para obter a série;
- não afirme que leu ou analisou os dados do arquivo.

## Mapa de tools

| Intenção                                                                                                             | Interpretação              | Tool sugerida         |
| -------------------------------------------------------------------------------------------------------------------- | -------------------------- | --------------------- |
| Valor atual, unidade, descrição, tipo, digital set, instrumenttag                                                    | Consulta pontual/metadados | `consultar_tag`       |
| Descobrir, localizar, procurar, encontrar ou listar tags por nome, descrição, equipamento, área ou termo de processo | Descoberta de tags         | `search_pi_points`    |
| Média, máximo, mínimo, soma, consumo, total por período                                                              | Agregação histórica        | `tag_statistics_tool` |
| Integral, derivada, taxa de variação, área sob curva                                                                 | Cálculo temporal explícito | `tag_calculus_tool`   |
| Compressão, exceção, compdev, excdev, archiving, scan, pointsource, location, atributos internos de uma tag PI       | Atributos de PI Point      | `tag_attributes_tool` |
| Valores minuto a minuto, série interpolada, valores brutos recorded, CSV com valores                                | Série temporal sem agregação | `generate_pi_tags_series_csv` |
| Disponibilidade da PI Web API (/dataservers), saúde do PIMS                                                          | Health check               | `status_pims_tool` (arguments={}) |

## Descoberta de tags

Use `search_pi_points` quando o usuário não souber o nome exato da tag e quiser encontrar tags relacionadas a uma descrição, equipamento, área, variável ou parte do nome.

**Importante**: consultas multi-token (ex.: "velocidade rb2") usam **AND explícito** da PI Web API Search Query Syntax: `Description:=*velocidade* AND Description:=*RB2*`. Isso torna todos os conceitos obrigatórios e não depende da ordem no Descriptor. Candidatos obtidos apenas por um termo único (ex.: `Description:=*RB2*`) não são válidos.

Use `consultar_tag` quando o usuário já informou uma tag específica e quer valor atual, unidade, descrição, tipo, digital set, instrumenttag ou metadados.

## Regra para perguntas naturais sobre tags

Quando o usuário perguntar algo como:

- "tem alguma tag de..."
- "existe alguma tag de..."
- "procure uma tag de..."
- "me retorne uma tag relacionada a..."
- "qual tag tem a ver com..."
- "quero uma tag de velocidade do forno"
- "tem alguma tag de velocidade do forno?"

a intenção é descoberta de tags. Use `search_pi_points`.

Para perguntas como:

- "tag de velocidade do forno"
- "tag de temperatura do forno"
- "tag de pressão"
- "tag de vazão"
- "tag de espessura"
- "tag de velocidade da linha"

a palavra `velocidade`, `temperatura`, `pressão`, `vazão` ou similar representa uma variável de processo. Não interpretar como cálculo temporal, derivada ou taxa de variação, a menos que o usuário peça explicitamente cálculo, derivada, integral ou taxa de mudança.

Exemplo:

```text
Usuário: "tem alguma tag de velocidade do forno?"

search_pi_points:
  query = "velocidade forno"
  search_mode = "auto"
```

Se o usuário mencionar explicitamente busca por descrição:

```text
Usuário: "procure tags com descrição velocidade"

search_pi_points:
  query = "velocidade"
  search_mode = "description"
```

Se o usuário mencionar explicitamente busca por nome:

```text
Usuário: "procure tags com nome LFI_RB3"

search_pi_points:
  query = "LFI_RB3"
  search_mode = "name"
```

## Consumo de vazão

Para consumo, interprete o resultado como volume acumulado. Uma tag em `Nm3/h` mede vazão; o consumo calculado no período é apresentado em unidade de volume, como `Nm3`.
Você precisa compreender a diferença entre unidade de engunit (unidade de engenharia) e unidade final do cálculo, não são a mesma coisa.

```text
tag_statistics_tool:
  data_method = "summary"
  summary_type = "Average"
  summary_duration = "1h"
  calculation_basis = "TimeWeighted"
  operation = "sum"
```

## Estatística simples

```text
tag_statistics_tool:
  data_method = "summary"
  summary_type = Average, Maximum, Minimum, Total, Count, Range ou StdDev
  summary_duration = usado quando o cálculo for por blocos
  calculation_basis = TimeWeighted para variáveis contínuas
```

## Cálculo temporal

```text
tag_calculus_tool:
  data_method = "interpolated"
  interval = "1m" ou outra frequência
  operation = "integral" ou "derivative"
  time_unit = "hour", "minute", "second" ou "none"
```

interval e group_by são parâmetros distintos:
- interval controla a resolução da coleta interpolada (ex: "1m" = 1 minuto entre amostras).
- group_by controla a granularidade dos buckets estatísticos da série retornada.
Ambos podem receber o valor "1m" com semânticas diferentes.
Exemplo: interval="1m" + group_by="1h" = coletar a cada minuto, consolidado em buckets horários.
Exemplo: group_by="1m" = buckets estatísticos de 1 minuto.
group_by aceita "1m", "1h", "1d", "1w", "1mo". Quando não especificado, usa "1h" (default).

## Períodos fechados

Para cálculos de dia, mês ou ano completos, use início inclusivo e fim exclusivo. Antes da execução, converta expressões como `mês passado`, `ontem`, `dia anterior`, `mês atual` e `ano passado` para `start_time` e `end_time` em ISO 8601 explícito com offset local.

Não chame `tag_statistics_tool` com períodos relativos como `*`, `*-1M`, `*-30d` ou `*-1d` quando a intenção for período fechado.

Exemplo de maio de 2026:

```text
start_time = 2026-05-01T00:00:00-03:00
end_time   = 2026-06-01T00:00:00-03:00
```

Formato esperado na chamada da tool:

```json
{
  "start_time": "2026-05-01T00:00:00-03:00",
  "end_time": "2026-06-01T00:00:00-03:00"
}
```

---

# CHUNK 02 - Fluxo base: tag para WebId

## Intenção

Use quando a consulta envolver valor atual, histórico, interpolado, summary, plot ou qualquer série temporal.

## Fluxo essencial

A PI Web API usa `WebId` para consultar streams. O nome da tag serve para localizar o PI Point.

```text
1. Montar path: \\PIMS\NOME_DA_TAG
2. Buscar PI Point: GET /points?path=\\PIMS\NOME_DA_TAG
3. Extrair WebId e metadados úteis.
4. Consultar o endpoint de stream usando /streams/{webId}/...
```

## Endpoint

```http
GET http://10.247.224.39/piwebapi/points?path=\\PIMS\LFI_RB3_VAZ_GN_TOTAL
```

## Campos mais úteis

```text
WebId             Identificador para /streams
Name              Nome da tag
Descriptor        Descrição
PointType         Tipo do point
EngineeringUnits  Unidade de engenharia
DigitalSetName    Digital set, quando aplicável
Links             URLs relacionadas, como Value, RecordedData e SummaryData
```

## Diretriz

Quando `Links` estiver disponível, ele pode ser usado para navegar para `Value`, `RecordedData`, `InterpolatedData`, `SummaryData`, `PlotData` e `Attributes`.

---

# CHUNK 03 - Valor atual de uma tag

## Intenção

Use quando o usuário pedir valor atual, último valor, snapshot, status atual ou “quanto está” uma tag.

## Fluxo

```text
1. GET /points?path=\\PIMS\TAG
2. Extrair WebId.
3. GET /streams/{webId}/value
4. Interpretar Value, Timestamp, Good e Questionable.
```

## Endpoint

```http
GET http://10.247.224.39/piwebapi/streams/{webId}/value
```

## Campos retornados pela API

```text
Timestamp          Data/hora do valor
Value              Valor retornado
UnitsAbbreviation  Unidade, quando disponível
Good               Qualidade boa quando true
Questionable       Valor suspeito quando true
Substituted        Valor substituído quando true
```

---

# CHUNK 04 - Metadados da tag

## Intenção

Use quando o usuário pedir unidade, descrição, tipo, digital set, span, zero, step ou metadados básicos.

## Endpoint

```http
GET http://10.247.224.39/piwebapi/points?path=\\PIMS\NOME_DA_TAG
```

## Campos principais

```text
Name              Nome
Path              Caminho completo
Descriptor        Descrição
PointClass        Classe
PointType         Tipo de dado
DigitalSetName    Nome do digital set
EngineeringUnits  Unidade de engenharia
Span              Faixa
Zero              Zero configurado
Step              Comportamento em degrau
DisplayDigits     Dígitos de exibição
```

## Exemplo reduzido

```json
{
  "Name": "LFI_RB3_VAZ_GN_TOTAL",
  "Descriptor": "VAZÃO DE GN TOTAL DO RB3",
  "PointType": "Float32",
  "EngineeringUnits": "Nm3/h",
  "DigitalSetName": "",
  "Step": false
}
```

## Otimização de payload

Use `selectedFields` para reduzir payload quando bastarem campos específicos:

```http
GET /points?path=\\PIMS\TAG&selectedFields=WebId;Name;Descriptor;PointType;DigitalSetName;EngineeringUnits;Links
```

---

# CHUNK 05 - Atributos do PI Point

## Intenção

Use para `instrumenttag`, `location1` a `location5`, `pointsource`, `engunits` como atributo ou outros atributos clássicos do PI Point.

## Fluxo

```text
1. Buscar PI Point por path.
2. Extrair WebId.
3. Consultar /points/{webId}/attributes.
4. Filtrar pelo atributo desejado.
```

## Endpoints

```http
GET /points/{webId}/attributes
GET /points/{webId}/attributes?name=instrumenttag
GET /points/{webId}/attributes?name=location1
```

## Exemplo de payload da API

```json
{
  "Items": [{ "Name": "instrumenttag", "Value": "FT-101" }]
}
```

## Diretriz

Quando o atributo vier vazio ou não existir, informe ausência de valor em vez de inferir um valor.

---

# CHUNK 06 - DigitalSetName e Digital States

## Intenção

Use para digital states, digital set, estados possíveis, ligado/desligado, aberto/fechado ou interpretação de status digital.

## Identificação

Consultar o PI Point e observar:

```text
PointType
DigitalSetName
Step
```

Tags digitais costumam ter `PointType=Digital`, `DigitalSetName` preenchido e comportamento discreto.

## Fluxo para estados digitais

```text
1. GET /points?path=\\PIMS\TAG
2. Ler DigitalSetName.
3. Buscar DataServer PIMS em /dataservers.
4. Listar /dataservers/{dataServerWebId}/enumerationsets.
5. Encontrar o set pelo nome.
6. Consultar /enumerationsets/{enumSetWebId}/enumerationvalues.
```

## Endpoints

```http
GET /dataservers
GET /dataservers/{dataServerWebId}/enumerationsets
GET /enumerationsets/{enumSetWebId}/enumerationvalues
```

## Valor digital

O valor atual pode vir como número ou objeto.

```json
{ "Value": 1, "Good": true }
```

ou:

```json
{ "Value": { "Name": "Ligado", "Value": 1 }, "Good": true }
```

---

# CHUNK 07 - Histórico bruto: recorded

## Intenção

Use quando o usuário pedir histórico bruto, eventos gravados, valores reais armazenados ou últimos eventos.

## Endpoint

```http
GET /streams/{webId}/recorded?startTime=*-8h&endTime=*&maxCount=500
```

## Parâmetros comuns

```text
startTime      Início
endTime        Fim
maxCount       Limite de eventos
boundaryType   Inside, Outside ou Interpolated
retrievalMode  Auto, Before, After, Exact, AtOrBefore, AtOrAfter
```

## Diretriz

`recorded` retorna eventos gravados. Para uma série em intervalo fixo, `interpolated` costuma ser mais adequado.

---

# CHUNK 08 - Valores interpolados

## Intenção

Use quando o usuário pedir valores a cada 1 minuto, 5 minutos, 1 hora ou outra frequência regular.

## Endpoint

```http
GET /streams/{webId}/interpolated?startTime=*-8h&endTime=*&interval=5m
```

## Parâmetros

```text
startTime   Início
endTime     Fim
interval    Espaçamento entre pontos: 1m, 5m, 15m, 1h
syncTime    Hora âncora, quando precisar alinhar intervalos
```

## Diretriz

Interpolado é adequado para amostragem regular. Para eventos exatamente gravados no PI, use `recorded`.

---

# CHUNK 09 - Summary: média, mínimo, máximo e total

## Intenção

Use para média, mínimo, máximo, soma, total, contagem, desvio padrão, percent good ou agregações por período.

## Endpoint

```http
GET /streams/{webId}/summary
```

## Exemplo

```http
GET /streams/{webId}/summary?startTime=-1d&endTime=*&summaryType=Average&summaryDuration=1h&calculationBasis=TimeWeighted
```

## summaryType comuns

```text
Average
Minimum
Maximum
Range
StdDev
Count
PercentGood
Total
All
```

## Diretrizes

```text
TimeWeighted  Variáveis contínuas: temperatura, pressão, vazão, nível.
EventWeighted Cada evento tem o mesmo peso.
summaryDuration divide o período em blocos, como 1h ou 1d.
```

---

# CHUNK 10 - Consumo de vazão usando médias horárias

## Intenção

Use para consumo de gás, consumo total, total de vazão, consumo mensal, consumo diário, consumo no período ou volume acumulado a partir de uma tag de vazão.

## Conceito

Consumo é uma grandeza acumulada. Quando a tag mede vazão, por exemplo `Nm3/h`, o resultado do cálculo de consumo representa volume no período.

```text
média horária em Nm3/h × 1h = volume em Nm3 no bloco
```

A unidade calculada deve ser inferida pela natureza do resultado. Para consumo, a unidade esperada é volume; para média de vazão, a unidade continua sendo vazão.

## Diretriz operacional

```text
data_method        summary
summary_type       Average
summary_duration   1h
calculation_basis  TimeWeighted
operation          sum
```

A soma considera os blocos horários válidos retornados pela consulta de summary.

## Endpoint

```http
GET /streams/{webId}/summary?startTime=2026-05-01T00:00:00-03:00&endTime=2026-06-01T00:00:00-03:00&summaryType=Average&summaryDuration=1h&calculationBasis=TimeWeighted
```

## Período mensal

Para cálculo de um mês completo, use o primeiro dia do mês calculado como início e o primeiro dia do mês seguinte como fim. Esse padrão representa início inclusivo e fim exclusivo.

Antes de chamar a tool, resolva o período para `start_time` e `end_time` em ISO 8601 explícito com offset local. Para mês fechado, não envie períodos relativos como `*`, `*-1M`, `*-30d` ou equivalentes.

```text
Maio/2026:
start_time = 2026-05-01T00:00:00-03:00
end_time   = 2026-06-01T00:00:00-03:00
```

Formato esperado na chamada da tool:

```json
{
  "start_time": "2026-05-01T00:00:00-03:00",
  "end_time": "2026-06-01T00:00:00-03:00"
}
```

---

# CHUNK 11 - Múltiplas tags: streamsets e batch

## Intenção

Use para consultar várias tags, combinar WebId + valor atual ou reduzir múltiplas chamadas HTTP.

## Streamsets ad-hoc

Use quando já houver WebIds:

```http
GET /streamsets/value?webId={id1}&webId={id2}
```

Também existem variações para `recorded` e `interpolated`.

## Batch

Use quando for preciso resolver points e consultar valores na mesma chamada.

```http
POST /batch
```

Exemplo reduzido:

```json
{
  "point_0": {
    "Method": "GET",
    "Resource": "http://10.247.224.39/piwebapi/points?path=\\PIMSTAG"
  },
  "value_0": {
    "Method": "GET",
    "ParentIds": ["point_0"],
    "Parameters": ["$.point_0.Content.WebId"],
    "Resource": "http://10.247.224.39/piwebapi/streams/{0}/value"
  }
}
```

## Diretriz

Trate o status de cada item do batch individualmente.

---

# CHUNK 12 - Buscar tag quando o nome não é exato

## Intenção

Use quando o usuário informar parte do nome, pedir tags parecidas, procurar tags por padrão ou listar candidatos.

## Fluxo

```text
1. GET /dataservers
2. Encontrar DataServer Name=PIMS.
3. GET /dataservers/{dataServerWebId}/points?nameFilter=*TRECHO*
4. Retornar candidatos curtos com nome e descriptor.
```

## Exemplo

```http
GET /dataservers/{dataServerWebId}/points?nameFilter=*VAZ_GN*
```

## Diretriz

Quando houver várias tags parecidas, apresente uma lista curta e peça desambiguação.

---

# CHUNK 13 - Tratamento de erros e qualidade

## Intenção

Use quando houver erro HTTP, tag não encontrada, WebId inválido, valor ruim, No Data, timeout ou falha de consulta.

## HTTP status

```text
200  Sucesso
400  Requisição inválida
401  Não autorizado
403  Sem permissão
404  Objeto não encontrado
500  Erro do servidor
```

## Qualidade do valor

```text
Good=false       Valor não confiável para cálculo.
Questionable    Valor disponível, mas suspeito.
Value=null      Ausência de valor útil.
```

## Diretrizes

- Preserve a informação de qualidade.
- Diferencie erro de API de valor ruim.
- Em cálculos, sinalize itens ruins ou a quantidade desconsiderada quando essa informação estiver disponível.

---

# CHUNK 14 - Strings de tempo e timezone

## Intenção

Use para interpretar hoje, ontem, últimas horas, mês fechado, período específico ou turno.

## Strings comuns

```text
*       agora
*-1h    uma hora atrás
*-8h    oito horas atrás
*-1d    um dia atrás
T       hoje à meia-noite
Y       ontem à meia-noite
```

## Datas absolutas

Quando o usuário falar em horário local, prefira ISO 8601 com offset:

```text
2026-06-15T00:00:00-03:00
2026-06-16T00:00:00-03:00
```

## Períodos fechados

Para períodos por dia, mês ou ano, use início inclusivo e fim exclusivo.

Em períodos fechados, `start_time` e `end_time` devem ser enviados em ISO 8601 explícito com offset local. Não envie `*`, `*-1M`, `*-1d`, `T`, `Y` ou outras strings relativas quando o usuário pedir um período calendário fechado, como `mês passado`, `maio de 2026`, `ontem`, `dia 15/06/2026` ou `ano passado`.

```text
Dia 15/06/2026:
start_time = 2026-06-15T00:00:00-03:00
end_time   = 2026-06-16T00:00:00-03:00
```

```text
Maio/2026:
start_time = 2026-05-01T00:00:00-03:00
end_time   = 2026-06-01T00:00:00-03:00
```

Formato esperado na chamada da tool:

```json
{
  "start_time": "2026-05-01T00:00:00-03:00",
  "end_time": "2026-06-01T00:00:00-03:00"
}
```

---

# CHUNK 15 - Codificação de URL

## Intenção

Use quando o path tiver caracteres especiais ou quando a URL falhar por codificação.

## Caracteres comuns

```text
\       %5C
|       %7C
#       %23
espaço  %20
:       %3A
```

## Diretriz

Ao usar biblioteca HTTP, passe o path como parâmetro de query e deixe a biblioteca codificar.

```python
requests.get(
    f"{base_url}/points",
    params={"path": r"\\PIMS\LFI_RB3_VAZ_GN_TOTAL"},
    timeout=30,
)
```

---

# CHUNK 16 - Decisão rápida de endpoint

## Intenção

Use como mapa curto de decisão.

```text
Valor atual:
  /points?path=... -> /streams/{webId}/value

Metadados:
  /points?path=...

Instrumenttag/location:
  /points?path=... -> /points/{webId}/attributes?name=...

Digital states:
  /points?path=... -> DigitalSetName -> enumerationvalues

Histórico bruto:
  /points?path=... -> /streams/{webId}/recorded

Intervalo fixo:
  /points?path=... -> /streams/{webId}/interpolated

Média/mínimo/máximo/total:
  /points?path=... -> /streams/{webId}/summary

Várias tags:
  batch ou streamsets
```

---

# CHUNK 17 - Exemplo Python: valor atual

## Intenção

Use como referência compacta para implementação.

```python
import requests

PIWEBAPI_URL = "http://10.247.224.39/piwebapi"
PI_SERVER = "PIMS"

def get_point(tag: str) -> dict:
    r = requests.get(
        f"{PIWEBAPI_URL}/points",
        params={"path": f"\\\\{PI_SERVER}\\{tag}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

def get_current_value(tag: str) -> dict:
    point = get_point(tag)
    value_url = point.get("Links", {}).get(
        "Value",
        f"{PIWEBAPI_URL}/streams/{point['WebId']}/value",
    )
    r = requests.get(value_url, timeout=30)
    r.raise_for_status()
    return {"point": point, "value": r.json()}
```

---

# CHUNK 18 - Exemplo Python: metadados e atributos

## Intenção

Use como referência compacta para buscar atributos clássicos.

```python
import requests

PIWEBAPI_URL = "http://10.247.224.39/piwebapi"
PI_SERVER = "PIMS"

def get_point(tag: str) -> dict:
    r = requests.get(
        f"{PIWEBAPI_URL}/points",
        params={"path": f"\\\\{PI_SERVER}\\{tag}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

def get_point_attribute(web_id: str, name: str):
    r = requests.get(
        f"{PIWEBAPI_URL}/points/{web_id}/attributes",
        params={"name": name},
        timeout=30,
    )
    r.raise_for_status()
    items = r.json().get("Items", [])
    return items[0].get("Value") if items else None
```

---

# CHUNK 19 - Diretrizes de qualidade e anti-padrões

## Intenção

Use para evitar interpretações frágeis em consulta e cálculo.

## Diretrizes

| Situação                           | Interpretação recomendada                             |
| ---------------------------------- | ----------------------------------------------------- |
| Stream solicitado pelo nome da tag | Primeiro resolver `WebId` com `/points?path=...`      |
| `DigitalSetName` vazio             | Tratar como ausência de digital set                   |
| `Good=false`                       | Considerar dado ruim, não valor numérico confiável    |
| `EngineeringUnits` vazio           | Responder sem inventar unidade                        |
| Atributo vazio                     | Informar que o atributo não foi encontrado/preenchido |
| Série em intervalo fixo            | Preferir `interpolated`                               |
| Eventos reais gravados             | Preferir `recorded`                                   |
| Busca com muitos candidatos        | Solicitar escolha da tag correta                      |
| Consumo de vazão                   | Explicar o critério de cálculo e a unidade inferida   |

---

# CHUNK 20 - Cálculos temporais: integral e derivada

## Intenção

Use quando o usuário pedir explicitamente integral, derivada, taxa de variação, área sob a curva ou velocidade de mudança.

## Anti-confusão com descoberta de tags

Não use este chunk quando o usuário estiver procurando uma tag que contenha a palavra `velocidade` ou uma variável chamada velocidade.

Exemplos que NÃO são cálculo temporal:

- "tem alguma tag de velocidade do forno?"
- "procure tags de velocidade"
- "me retorne uma tag de velocidade da linha"
- "quero uma tag de velocidade"
- "existe tag de velocidade do forno?"

Nesses casos, a intenção é descoberta de tags. Use `search_pi_points` e consulte os chunks de descoberta de tags por `/points/search`, especialmente CHUNK 22 e CHUNK 23.

Use `tag_calculus_tool` somente quando o usuário pedir cálculo matemático temporal de forma explícita, como:

- "calcule a derivada da tag"
- "calcule a taxa de variação"
- "integre a vazão"
- "qual a área sob a curva?"
- "velocidade de mudança da variável"

## Tool

`tag_calculus_tool` é voltada para cálculo temporal matemático explícito.

## Parâmetros principais

```text
operation    integral ou derivative
data_method  geralmente interpolated
interval     frequência de amostragem, como 1m ou 5m
time_unit    unidade temporal do cálculo: second, minute, hour ou none
start_time   início do período
end_time     fim do período
```

## Exemplo compacto

```text
Usuário: "Integre VAZAO_LINHA_01 nas últimas 6 horas com pontos a cada 5 minutos"

tag_calculus_tool:
  tags = ["VAZAO_LINHA_01"]
  operation = "integral"
  data_method = "interpolated"
  interval = "5m"
  time_unit = "hour"
  start_time = "*-6h"
  end_time = "*"
```

## Diferença de intenção

| Pedido                      | Interpretação                          | Tool sugerida         |
| --------------------------- | -------------------------------------- | --------------------- |
| consumo total de vazão      | consolidação operacional por período   | `tag_statistics_tool` |
| integral da vazão           | cálculo matemático da área sob a curva | `tag_calculus_tool`   |
| soma dos valores horários   | agregação dos blocos retornados        | `tag_statistics_tool` |
| taxa de variação por minuto | derivada temporal                      | `tag_calculus_tool`   |
| tag de velocidade do forno  | descoberta de tag                      | `search_pi_points`    |
| procurar tags de velocidade | descoberta de tag                      | `search_pi_points`    |

## Unidade

`time_unit` descreve unidade temporal do cálculo, não a unidade de engenharia da tag. A unidade final do cálculo é inferida combinando unidade da tag, operação e unidade temporal.

---

# CHUNK 21 - RAG e recuperação recomendada

## Intenção

Use para orientar montagem de contexto em um RAG com top-k baixo.

## Diretriz

Mantenha um chunk base com o fluxo `tag -> WebId -> endpoint` e recupere chunks específicos pela intenção atual.

## Composição de contexto final

```text
1. Chunk base de fluxo PI Web API.
2. Chunk específico da intenção: valor atual, summary, digital states, consumo, erro etc.
3. Chunk de qualidade ou seleção de tool, quando útil.
```

## Query de recuperação

Monte a query com a mensagem atual, tags detectadas e termos técnicos da intenção. Evite usar stacktraces ou erros antigos como texto principal da busca.

Exemplo:

```text
consumo vazão mês passado
Tags: LFI_RB3_VAZ_GN_TOTAL
Termos: summary Average 1h TimeWeighted consumo start_time end_time ISO período fechado
```

---

# CHUNK 22 - PI Web API: descoberta de PI Points por nome ou descrição usando `/points/search`

## Intenção

Use este chunk quando precisar descobrir tags no PI Data Archive por nome de tag, descrição textual, equipamento, área, variável de processo ou termo informado pelo operador.

Este chunk é especialmente importante para perguntas naturais como:

- "tem alguma tag de velocidade do forno?"
- "me retorne uma tag que tenha a ver com velocidade do forno"
- "procure tags de velocidade"
- "procure tags com descrição velocidade"
- "quais tags têm descrição relacionada a temperatura?"
- "existe tag de pressão do forno?"
- "não sei o nome da tag, mas é sobre velocidade"
- "quero uma tag de vazão do RB3"

Essas perguntas devem usar `search_pi_points`, não `tag_calculus_tool`.

## Endpoint principal

```http
GET {PI_WEB_API_BASE_URL}/points/search?dataServerWebId={DATA_SERVER_WEB_ID}&query={SEARCH_QUERY}&maxCount={N}
```

No ambiente PIMS validado:

```text
PI_WEB_API_BASE_URL = http://10.247.224.39/piwebapi
PI_SERVER_NAME = PIMS
DATA_SERVER_WEB_ID = F1DSxhF1MCtATE6DjgaMSVY2ggUElNUw
```

O `DATA_SERVER_WEB_ID` deve ser obtido dinamicamente pelo endpoint:

```http
GET http://10.247.224.39/piwebapi/dataservers?name=PIMS
```

Não hardcodar o WebId em código de produção se houver função de descoberta ou configuração disponível.

## Busca por descrição

Para buscar por descrição, use o filtro `Description`.

```http
GET http://10.247.224.39/piwebapi/points/search?dataServerWebId=F1DSxhF1MCtATE6DjgaMSVY2ggUElNUw&query=Description:=*velocidade*&maxCount=5
```

Regras:

- Usar `Description`, não `Descriptor`.
- O JSON retornado pelo PI Point pode ter campo `Descriptor`, mas a sintaxe de busca usa `Description`.
- Usar o parâmetro `query`, não `q`.
- Informar `dataServerWebId`.
- Usar `maxCount=5` para não estourar o contexto do agente.
- Para busca parcial, envolver o termo com wildcard `*`.

Exemplo para a tool:

```text
search_pi_points:
  query = "velocidade"
  search_mode = "description"
```

Query enviada à PI Web API:

```text
Description:=*velocidade*
```

## Busca por nome

Para buscar por nome da tag, use o filtro `Name`.

```http
GET http://10.247.224.39/piwebapi/points/search?dataServerWebId=F1DSxhF1MCtATE6DjgaMSVY2ggUElNUw&query=Name:=*LFI_RB3*&maxCount=5
```

Exemplo para a tool:

```text
search_pi_points:
  query = "LFI_RB3"
  search_mode = "name"
```

Query enviada à PI Web API:

```text
Name:=*LFI_RB3*
```

## Busca automática com AND explícito

Para `search_mode="auto"`, consultas multi-token (2+ conceitos significativos) usam **AND explícito** da PI Web API Search Query Syntax. Cada conceito é obrigatório; consultas de termo único não geram resultado válido.

### Consultas de 1 token

```text
Description:=*termo*
```
ou:
```text
Name:=*termo*
```

### Consultas de 2+ tokens — AND explícito

```text
Description:=*velocidade* AND Description:=*RB2*
```

Isso significa:
- A descrição deve conter "velocidade" **E** "RB2";
- a ordem dos termos no Descriptor não importa;
- caracteres podem existir entre eles.

### O que NÃO usar como estratégia principal

`Description:="*velocidade rb2*"` — exige os termos na mesma sequência textual.

`Description:=*velocidade*RB2*` — exige ordem fixa (velocidade antes de RB2).

`Description:=*RB2*` ou `Description:=*velocidade*` — cada consulta ignora um dos conceitos.

### Exemplo completo

```text
Usuário: "tem alguma tag de velocidade do forno?"

search_pi_points:
  query = "velocidade forno"
  search_mode = "auto"
```

Query(s) PI geradas internamente:

```text
Q1: Description:=*velocidade* AND Description:=*forno*
Q2: Name:=*velocidade* AND Name:=*forno*
Q3: Name:=*forno* AND Description:=*velocidade*   (contexto em Name, variável em Description)
Q4: Description:=*forno* AND Name:=*velocidade*   (inverso controlado)
```

As 4 queries são executadas em paralelo. Resultados são unidos, deduplicados, validados por filtragem local (todos os conceitos devem estar em `Name + Descriptor` da tag), classificados por confidence e ranqueados. Apenas confidence high e medium são retornados.

O agente recebe no máximo 5 resultados.

## Fallback por nameFilter

O endpoint `nameFilter` também funciona para busca por nome:

```http
GET http://10.247.224.39/piwebapi/dataservers/F1DSxhF1MCtATE6DjgaMSVY2ggUElNUw/points?nameFilter=*velocidade*&maxCount=5
```

Use `nameFilter` como fallback ou apoio para busca por nome. Não usar `nameFilter` como substituto silencioso de busca por descrição.

## Regras obrigatórias

- Para descoberta de tags, usar `search_pi_points`.
- Para busca por descrição, usar `/points/search` com `dataServerWebId` e `query=Description:=*termo*`.
- Para busca por nome, usar `/points/search` com `dataServerWebId` e `query=Name:=*termo*`.
- Usar `query`, não `q`.
- Usar `Description`, não `Descriptor`.
- Não enviar texto cru como `query=velocidade` quando a intenção for busca por descrição.
- Não combinar `Name` e `Description` na mesma query esperando comportamento de `OR`.
- Retornar no máximo 5 tags ao agente.
- Se houver muitos candidatos, pedir ao operador mais contexto, como área, equipamento ou parte do nome da tag.

## Exemplo recomendado em Python

```python
params = {
    "dataServerWebId": data_server_web_id,
    "query": "Description:=*velocidade*",
    "maxCount": 5,
}

response = requests.get(
    f"{PI_WEB_API_BASE_URL}/points/search",
    params=params,
    timeout=30,
    verify=False,
)
```

---

# CHUNK 23 - PI Web API Search Query Syntax: regras para montar `query`

## Intenção

Use este chunk para montar corretamente o parâmetro `query` do endpoint `/points/search`.

A PI Web API usa Search Query Syntax baseada em AFSearch para o parâmetro `query`. Não tratar `query` como pesquisa livre estilo Google.

## Endpoint

```http
GET /points/search?dataServerWebId={DATA_SERVER_WEB_ID}&query={SEARCH_QUERY}&maxCount={N}
```

Parâmetros obrigatórios no ambiente PIMS:

```text
dataServerWebId  WebId do DataServer PIMS
query            expressão de busca PI Point Search Syntax
maxCount         limite de resultados
```

No agente, usar `maxCount=5` para descoberta de tags.

## Filtros principais para PI Points

```text
Name:=*TERMO*          busca pelo nome da tag
Description:=*TERMO*   busca pela descrição textual da tag
```

Regras:

- Usar `Name` para nome de tag.
- Usar `Description` para descrição.
- Não usar `Descriptor` na query de busca.
- O retorno da API pode conter campo `Descriptor`, mas a sintaxe de busca usa `Description`.
- Usar `query`, não `q`.
- Usar `dataServerWebId`.
- Não usar busca crua quando a intenção é nome ou descrição.
- Wildcard `*` significa zero ou mais caracteres.
- Wildcard `?` significa exatamente um caractere.
- Sem wildcard, a comparação tende a ser muito restritiva.
- Não pode haver espaço entre o nome do filtro, o separador e o operador.
- Usar `Description:=*termo*`, não `Description := *termo*`.

## Busca por descrição

Para perguntas em linguagem natural como:

- "tem alguma tag de velocidade do forno?"
- "procure tags com descrição velocidade"
- "quais tags têm descrição de temperatura?"
- "existe alguma tag de pressão do forno?"

usar busca por descrição como primeira tentativa.

```text
Description:=*velocidade*
```

Exemplo:

```http
GET /points/search?dataServerWebId={DATA_SERVER_WEB_ID}&query=Description:=*velocidade*&maxCount=5
```

## Busca por nome

Para perguntas que indicam parte do nome técnico da tag, como:

- "procure tags LFI_RB3"
- "tags com nome VEL_FORNO"
- "tag que começa com LFS_DC1"

usar busca por nome.

```text
Name:=*LFI_RB3*
```

Exemplo:

```http
GET /points/search?dataServerWebId={DATA_SERVER_WEB_ID}&query=Name:=*LFI_RB3*&maxCount=5
```

## Filtros conjuntivos com AND

Para consultas multi-token (ex.: "velocidade rb2"), usar **AND explícito** entre filtros do mesmo campo:

```text
Description:=*velocidade* AND Description:=*RB2*
```

Significa: Description contém "velocidade" **E** Description contém "RB2". Ambos são obrigatórios. A ordem no Descriptor não importa.

### O que NÃO fazer

```text
Description:="*velocidade rb2*"
```
- exige a sequência textual exata (depende da ordem).

```text
Name:=*velocidade* Description:=*velocidade*
```
- combina Name e Description na mesma query; significa AND entre campos, não OR.

```text
Description:=*RB2*
```
- como resultado final, ignora o conceito "velocidade". Fallback de termo único não é válido.

### Modo automático (auto)

O modo automático executa um conjunto controlado de queries independentes (não combinadas em uma única string):

```text
Q1. Description:=*t1* AND Description:=*t2* [...]
Q2. Name:=*t1* AND Name:=*t2* [...]
Q3. Name:=*contexto* AND Description:=*variável*   (quando inequívoco)
Q4. Description:=*contexto* AND Name:=*variável*   (inverso controlado)
```

As queries são executadas em paralelo. Resultados são unidos, deduplicados por WebId, validados por filtragem local, classificados por confidence (high/medium/low) e ranqueados. Low é descartado. Apenas high e medium são retornados.

**Hard cap**: máximo 5 resultados públicos.

## Mapeamento recomendado para a tool `search_pi_points`

```text
search_mode="description":
  1 token: Description:=*{token}*
  N tokens: Description:=*{t1}* AND Description:=*{t2}* [...]

search_mode="name":
  1 token: Name:=*{token}*
  N tokens: Name:=*{t1}* AND Name:=*{t2}* [...]

search_mode="auto":
  ≤4 queries paralelas:
    Q1. Description:=*{t1}* AND Description:=*{t2}* [...]
    Q2. Name:=*{t1}* AND Name:=*{t2}* [...]
    Q3. Name:=*{contexto}* AND Description:=*{variável}*
    Q4. (inverso controlado)
  unir, deduplicar por WebId, filtrar localmente, classificar confidence, ranquear, cap 5

search_mode="query":
  aceitar uma query avançada pronta, por exemplo:
  Description:=*velocidade* AND Name:=*RB3*
```

Se `search_mode="query"` receber texto simples sem `Description:=` ou `Name:=`, tratar como busca automática.

## Termos com espaço

Para termos com espaço, a busca por frase inteira pode ser restritiva dependendo da sintaxe e do comportamento do servidor.

Exemplo:

```text
Description:=*velocidade forno*
```

Se não retornar resultados suficientes, a tool pode tentar termos principais ou padrões técnicos equivalentes, como:

```text
Description:=*velocidade*
Name:=*VEL*FORNO*
Name:=*FRN*VELOCIDADE*
```

Para a pergunta:

```text
tem alguma tag de velocidade do forno?
```

a intenção continua sendo descoberta de tags. Use `search_pi_points`, não `tag_calculus_tool`.

## Fallback

Se `/points/search` falhar por indisponibilidade ou erro operacional em busca por nome, usar:

```http
GET /dataservers/{dataServerWebId}/points?nameFilter=*TERMO*&maxCount=5
```

Atenção:

- `nameFilter` busca por nome da tag.
- Não usar `nameFilter` como substituto silencioso de busca por descrição.
- `nameFilter` deve ser fallback ou apoio para busca por nome.
- Se houver fallback, manter o limite de 5 resultados.

## Limite de resultados

A tool deve retornar no máximo 5 tags para evitar estourar o contexto do agente.

Mesmo que o usuário peça 20, 50 ou 100 resultados, a resposta da tool deve cortar em 5 e orientar o operador a refinar a busca.

Exemplo de resposta esperada:

```text
Encontrei até 5 tags candidatas:
1. LFI_RB1_FRN_VELOCIDADE_LIM_INF — VELOCIDADE FORNO LIMITE INFERIOR
2. LFI_RB1_FRN_VELOCIDADE_LIM_OBJ — VELOCIDADE FORNO LIMITE OBJETIVADO
3. LFI_RB1_FRN_VELOCIDADE_LIM_SUP — VELOCIDADE FORNO LIMITE SUPERIOR

Para refinar, informe área, equipamento ou parte do nome da tag.
```

---

# CHUNK 24 - PI Web API: atributos de PI Point, compressão e exceção

## Intenção

Use para consultar atributos internos do PI Point relacionados a compressão,
exceção, scan, archiving, pointsource, instrumenttag, scaling, interface e security.

## Endpoint

```http
GET /points/{webId}/attributes
```

## Fluxo

1. Buscar PI Point por path (`/points?path=\\PIMS\TAG`).
2. Extrair WebId.
3. Chamar `/points/{webId}/attributes` (sem `?name=` para obter todos os atributos).

## Grupos de atributos

| Grupo         | Atributos                                                                 |
| ------------- | ------------------------------------------------------------------------- |
| auto          | compressing, compdev, compdevpercent, compmin, compmax, excdev, excdevpercent, excmin, excmax, scan, pointsource, instrumenttag |
| compression   | compressing, compdev, compdevpercent, compmin, compmax                   |
| exception     | excdev, excdevpercent, excmin, excmax                                     |
| archive       | archiving, scan, shutdown, step, future                                   |
| identity      | tag, descriptor, engunits, pointtype, pointsource, instrumenttag, digitalset |
| scaling       | zero, span, typicalvalue, displaydigits, squareroot, convers              |
| interface     | location1..5, exdesc, sourcetag, srcptid                                  |
| security      | ptsecurity, datasecurity, ptaccess, dataaccess, ptowner, ptgroup, dataowner, datagroup |
| all           | Todos os atributos retornados pela API                                    |

## Aliases aceitos

| Alias comum          | Grupo canônico  |
| -------------------- | ---------------- |
| `metadata`, `identidade`, `descrição`, `unidade` | `identity` |
| `compressão`, `compressao`, `compdev`, `compmax` | `compression` |
| `exceção`, `excecao`, `excesso`, `excessao`, `execeção`, `exececao` | `exception` |
| `arquivamento`, `archiving`, `scan` | `archive` |
| `escala`, `zero`, `span`, `typicalvalue` | `scaling` |
| `location`, `sourcetag` | `interface` |
| `segurança`, `seguranca` | `security` |

## Interpretação operacional

| Atributo        | Significado                            | Valor típico         |
| --------------- | -------------------------------------- | -------------------- |
| compressing     | Compressão ativada?                    | 1=ativada / 0=desativada |
| compdev         | Desvio de compressão (segundos)        | 0.05 segundos        |
| compdevpercent  | Percentual do desvio de compressão     | 10                   |
| compmin         | Mínimo para compressão (segundos)      | 0 segundos           |
| compmax         | Máximo para compressão (segundos)      | 300 segundos         |
| excdev          | Desvio de exceção (segundos)           | 0.1 segundos         |
| excdevpercent   | Percentual do desvio de exceção        | 5                    |
| excmin          | Mínimo para exceção (segundos)         | -10 segundos         |
| excmax          | Máximo para exceção (segundos)         | 350 segundos         |
| scan            | Escaneamento ativo?                    | 1=ligado / 0=desligado |
| archiving       | Arquivamento ativo?                    | 1=ativado / 0=desativado |
| pointsource     | Fonte do ponto                         | PIMS, OPC, etc.      |
| instrumenttag   | Tag do instrumento de campo            | FT-101               |

## Regras de resposta

- A tool retorna apenas os atributos solicitados (texto curto, 1 linha por atributo).
- Não retornar `Links`, `Self`, `Point` ou JSON bruto.
- Se o usuário pedir valor atual da tag, usar `consultar_tag`, não esta tool.
- Atributo não configurado: exibir `(não configurado)`.

---

# CHUNK 25 - Política de entrega de artefatos (Google Drive)

## Quando usar

Resultados tabulares, séries temporais, logs completos, timelines e
relatórios multi-tag podem ser entregues como arquivo CSV no Google Drive.

O agente não precisa chamar tools de exportação — o arquivo é gerado
automaticamente pelo próprio service antes do retorno MCP.

## Manifesto compacto (ArtifactManifest)

Quando uma tool retorna `delivery: drive_artifact`, o conteúdo é um manifesto:

```json
{
  "schema_version": "1.0",
  "status": "success | partial_success | no_data | error",
  "delivery": "drive_artifact",
  "tool_name": "tag_statistics",
  "request_summary": {
    "tags_requested": 1,
    "tags_processed": 1,
    "start_time": "...",
    "end_time": "...",
    "operation": "mean",
    "group_by": "1m",
    "output_mode": "series"
  },
  "artifact": {
    "format": "csv",
    "filename": "pi_chat_dev_tag_statistics_20260728T145300Z_a1b2c3.csv",
    "mime_type": "text/csv",
    "row_count": 44640,
    "column_count": 5,
    "size_bytes": 1234567,
    "view_url": "https://drive.google.com/file/d/.../view"
  },
  "warnings": [],
  "errors_summary": []
}
```

## Limites

- Máximo de 1.000.000 linhas por arquivo.
- Máximo de 100 MB por arquivo.
- Máximo de 50 colunas.
- Manifesto serializado < 8 KB.
- Resultados escalares continuam inline (sem mudança).

## Regras de resposta para o agente

- Apresente `view_url` ao usuário.
- Não chame a tool novamente para obter a série.
- Não chame `export_csv_to_drive_tool` — o arquivo já foi gerado.
- Não afirme que leu ou analisou dados que não recebeu.
- O download pode ser realizado pela interface nativa do Google Drive após o arquivo ser aberto.

---

# CHUNK 26 - generate_pi_tags_series_csv: séries temporais sem agregação

## Intenção

Tool dedicada a consultar valores temporais de tags PI sem aplicar operação
estatística, gerar CSV completo, publicar no Google Drive e retornar apenas
um ArtifactManifest compacto.

NÃO usar para operações estatísticas (média, máximo, mínimo, soma, consumo).
Para esses, use `tag_statistics`.

## Contrato

| Parâmetro | Tipo | Default | Restrições |
|---|---|---|---|
| `tags` | `list[str]` | obrigatório | 1 a 10 tags, sem duplicatas |
| `start_time` | `str` | obrigatório | PI tokens (`*`, `*-1h`, `T`, `Y`) ou ISO 8601 |
| `end_time` | `str` | `"*"` | Janela `[start, end)` |
| `data_method` | `str` | `"interpolated"` | `"interpolated"` ou `"recorded"` |
| `interval` | `str \| None` | `None` | `"1m"`, `"5m"`, `"1h"`, etc. Obrigatório para interpolated. Proibido para recorded. |

Não possui parâmetro `operation`.

## Roteamento

| Pedido do usuário | Configuração |
|---|---|
| "valores minuto a minuto" | data_method=interpolated, interval=1m |
| "valores a cada 5 minutos" | data_method=interpolated, interval=5m |
| "valores brutos", "eventos gravados" | data_method=recorded |
| "série interpolada" | data_method=interpolated |
| "CSV com valores" | data_method=interpolated ou recorded conforme contexto |

## Exemplo de chamada

```json
{
  "tags": ["LFS_RB2_VELOPROC"],
  "start_time": "*-1h",
  "end_time": "*",
  "data_method": "interpolated",
  "interval": "1m"
}
```

## Saída

A tool sempre retorna um ArtifactManifest compacto (em caso de sucesso) ou
um resultado inline `no_data`. Nenhuma linha de dados é retornada ao LLM.

## Diferença para tag_statistics

| Característica | generate_pi_tags_series_csv | tag_statistics |
|---|---|---|
| Propósito | Valores temporais brutos/interpolados | Agregados estatísticos |
| Parâmetro operation | Não possui | Obrigatório |
| data_method | interpolated ou recorded | summary (para série estatística) |
| Saída | CSV completo no Drive | Manifesto compacto |
| Agregação | Nenhuma | Média, máximo, mínimo, soma, etc. |

## Limites

- Máximo de 10 tags por chamada.
- Período máximo de 31 dias.
- Máximo de 1.000.000 de linhas por CSV.
- Máximo de 100 MiB por arquivo.
- Times mínimos suportados: 1s, 1m, 5m, 15m, 1h, 1d, etc.
