# CHUNK 01 - Chunk fixo: seleção de tool e resumo operacional

## Intenção

Use como contexto base para orientar seleção de ferramenta e parâmetros.

## Mapa de tools

| Intenção                                                          | Interpretação              | Tool sugerida         |
| ----------------------------------------------------------------- | -------------------------- | --------------------- |
| Valor atual, unidade, descrição, tipo, digital set, instrumenttag | Consulta pontual/metadados | `consultar_tag_tool`  |
| Média, máximo, mínimo, soma, consumo, total por período           | Agregação histórica        | `tag_statistics_tool` |
| Integral, derivada, taxa de variação, área sob curva              | Cálculo temporal explícito | `tag_calculus_tool`   |
| Status do PIMS, servidores, logs                                  | Consulta operacional       | `status_pims_tool`    |

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
