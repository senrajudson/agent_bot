# Guia de Referência PI Web API

Referência construída para agentes que consultam dados do PI System via PI Web API. Este guia foca em **leitura de dados e informações** — sem manutenção, sem administração, sem gravações.

**URL Base**: `http://10.247.224.39/piwebapi`

---

## Índice

1. [Início Rápido](#início-rápido)
2. [Encontrando Points e Elements](#encontrando-points-e-elements)
3. [Lendo Dados de Séries Temporais](#lendo-dados-de-séries-temporais)
4. [Recuperação de Dados em Lote](#recuperação-de-dados-em-lote)
5. [Consultando Event Frames](#consultando-event-frames)
6. [Navegação na Hierarquia AF](#navegação-na-hierarquia-af)
7. [Operações de Busca](#operações-de-busca)
8. [Informações do Sistema](#informações-do-sistema)
9. [Tratamento de Erros](#tratamento-de-erros)
10. [Padrões Comuns](#padrões-comuns)

---

## Início Rápido

### Obter valor atual de um PI Point por caminho
```bash
curl -s "http://10.247.224.39/piwebapi/points?path=\\PIMS\sinusoid" | jq '.WebId'
```

### Obter o valor usando o WebId a partir dos Links
```bash
# Use o link Value da resposta:
curl -s "http://10.247.224.39/piwebapi/streams/F1DPxhF1MCtATE6DjgaMSVY2ggh0AAAAAU1NU1xMRklfUkIzX1pBW19IV19UT1RBTA/value"
```

### Obter dados históricos
```bash
curl -s "http://10.247.224.39/piwebapi/streams/{webId}/recorded?startTime=-1d&endTime=*"
```

---

## Encontrando Points e Elements

### PI Point por Caminho
```
GET http://10.247.224.39/piwebapi/points?path=\\PIMS\sinusoid
```
Retorna: WebId, Name, PointClass, PointType, EngineeringUnits, Span, Zero, Step e links para os dados.

Exemplo de resposta de `http://10.247.224.39/piwebapi/points?path=\\PIMS\LFI_RB3_VAZ_GN_TOTAL`:
```json
{
  "WebId": "F1DPxhF1MCtATE6DjgaMSVY2ggh0AAAAAU1NU1xMRklfUkIzX1pBW19IV19UT1RBTA",
  "Name": "LFI_RB3_VAZ_GN_TOTAL",
  "Path": "\\\\pims\\LFI_RB3_VAZ_GN_TOTAL",
  "PointClass": "classic",
  "PointType": "Float32",
  "EngineeringUnits": "Nm3/h",
  "Span": 12000.0,
  "Zero": 0.0,
  "Step": false
}
```

### AF Element por Caminho
```
GET http://10.247.224.39/piwebapi/elements?path=\\PIMS\MyDB\MyElement
```

### AF Attribute por Caminho
```
GET http://10.247.224.39/piwebapi/attributes?path=\\PIMS\MyDB\MyElement|Temperature
```

### Obter Attributes de um Element
```
GET http://10.247.224.39/piwebapi/elements/{webId}/attributes
```

### Obter Valor de um Attribute (Não-Série Temporal)
```
GET http://10.247.224.39/piwebapi/attributes/{webId}/value
```

---

## Lendo Dados de Séries Temporais

Todos os dados de séries temporais são acessados através dos endpoints **Stream**. O WebId é obtido a partir de um PI Point ou de um Attribute com referência de dados PI Point.

### Valor Atual
```
GET http://10.247.224.39/piwebapi/streams/{webId}/value
```
Retorna o valor mais recente com timestamp, qualidade e unidades.

### Valores Gravados (Dados Históricos Brutos)
```
GET http://10.247.224.39/piwebapi/streams/{webId}/recorded
  ?startTime=-1d
  &endTime=*
  &maxCount=1000
```
| Parâmetro | Descrição |
|-----------|-----------|
| `startTime` | Início do intervalo de tempo (string de tempo PI) |
| `endTime` | Fim do intervalo de tempo (`*` = agora) |
| `maxCount` | Máximo de valores retornados |
| `boundaryType` | `Inside` (padrão) ou `Outside` |
| `retrievalMode` | `Auto`, `AtOrBefore`, `Before`, `AtOrAfter`, `After`, `Exact` |

### Valores Interpolados (Preenchimento de Lacunas)
```
GET http://10.247.224.39/piwebapi/streams/{webId}/interpolated
  ?startTime=-1d
  &endTime=*
  &interval=1h
```
| Parâmetro | Descrição |
|-----------|-----------|
| `interval` | Intervalo entre os valores (`15m`, `1h`, `1d`) |
| `syncTime` | Hora âncora para prevenir deriva do intervalo |

### Valores para Gráfico (Plot)
```
GET http://10.247.224.39/piwebapi/streams/{webId}/plot
  ?startTime=-8h
  &endTime=*
  &intervals=500
```
Retorna um subconjunto otimizado de valores para exibição em gráficos.

### Valores Resumidos (Agregações)
```
GET http://10.247.224.39/piwebapi/streams/{webId}/summary
  ?startTime=-1d
  &endTime=*
  &summaryType=Average
  &summaryType=Maximum
```
| `summaryType` | Descrição |
|---------------|-----------|
| `Total` | Totalização |
| `Average` | Média |
| `Minimum` | Valor mínimo |
| `Maximum` | Valor máximo |
| `Range` | Amplitude (Max - Min) |
| `StdDev` | Desvio padrão |
| `Count` | Quantidade de eventos |
| `PercentGood` | % do tempo com dados válidos |
| `All` | Todos os tipos de resumo |

Parâmetros adicionais:
- `calculationBasis`: `TimeWeighted` (padrão) ou `EventWeighted`
- `duration` (duração): Para resumos por intervalo de tempo (ex: `1h` para médias horárias)
- `timeType`: `Auto`, `EarliestTime` ou `MostRecentTime`

---

## Recuperação de Dados em Lote

Stream Sets recuperam dados de **múltiplos attributes** em uma única chamada.

### Hierárquico (Mesmo Element Pai)
```
GET http://10.247.224.39/piwebapi/streamsets/{webId}/value
GET http://10.247.224.39/piwebapi/streamsets/{webId}/recorded
GET http://10.247.224.39/piwebapi/streamsets/{webId}/interpolated
GET http://10.247.224.39/piwebapi/streamsets/{webId}/summaries
```
| Parâmetro | Descrição |
|-----------|-----------|
| `fieldNameFilter` | Nomes de attributes separados por vírgula (ex: `Temperature,Pressure`) |
| `categoryNameFilter` | Filtrar por categoria do attribute |

### Ad-Hoc (Points Arbitrários)
```
GET http://10.247.224.39/piwebapi/streamsets/value?webId={id1}&webId={id2}
GET http://10.247.224.39/piwebapi/streamsets/recorded?webId={id1}&webId={id2}
GET http://10.247.224.39/piwebapi/streamsets/interpolated?webId={id1}&webId={id2}
```
**Quando usar**: Quando precisar de dados de points não relacionados em diferentes elements.

---

## Consultando Event Frames

### Event Frames de um Element
```
GET http://10.247.224.39/piwebapi/elements/{webId}/eventframes
```

### Event Frames de um Database
```
GET http://10.247.224.39/piwebapi/assetdatabases/{webId}/eventframes
```

### Buscar Event Frames
```
GET http://10.247.224.39/piwebapi/assetdatabases/{webId}/eventframes
  ?searchQuery=Name:=Shutdown* Template:ProcessTemplate
```

| Filtro de Busca | Exemplo |
|------------------|---------|
| `Name:=Pattern*` | Nome com curingas (wildcards) |
| `Template:TemplateName` | Filtrar por template |
| `Category:CategoryName` | Filtrar por categoria |
| `Element:ParentName` | Filtrar por element pai |
| `Start:>-1w` | Iniciado há mais de 1 semana |
| `End:<*` | Finalizado antes de agora |
| `InProgress:true` | Atualmente ativo |
| `Severity:Critical` | Filtrar por severidade |

### Modos de Busca de Event Frames
| Modo | Descrição |
|------|-----------|
| `StartInclusive` | Hora de início dentro do intervalo |
| `EndInclusive` | Hora de fim dentro do intervalo |
| `Inclusive` | Tanto início quanto fim dentro do intervalo |
| `Overlapped` | Sobrepõe com o intervalo |
| `InProgress` | Iniciado no intervalo, sem data de fim |

### Obter Attributes de um Event Frame
```
GET http://10.247.224.39/piwebapi/eventframes/{webId}/attributes
```

### Obter Elements Referenciados de um Event Frame
```
GET http://10.247.224.39/piwebapi/eventframes/{webId}/referencedelements
```

---

## Navegação na Hierarquia AF

### Listar Asset Servers
```
GET http://10.247.224.39/piwebapi/assetservers
```

### Obter Databases de um Server
```
GET http://10.247.224.39/piwebapi/assetservers/{webId}/databases
```

### Obter Elements de um Database
```
GET http://10.247.224.39/piwebapi/assetdatabases/{webId}/elements
```

### Obter Child Elements
```
GET http://10.247.224.39/piwebapi/elements/{webId}/elements
```

### Obter Element Templates
```
GET http://10.247.224.39/piwebapi/assetdatabases/{webId}/elementtemplates
```

### Padrão de Navegação (HATEOAS)
Toda resposta inclui um objeto `Links`. Siga os links em vez de construir URLs manualmente:
```json
{
  "WebId": "AbTG2yC4KjNRxe...",
  "Name": "MyElement",
  "Links": {
    "Self": "http://10.247.224.39/piwebapi/elements/AbTG2yC4KjNRxe...",
    "Attributes": "http://10.247.224.39/piwebapi/elements/AbTG2yC4KjNRxe.../attributes",
    "Elements": "http://10.247.224.39/piwebapi/elements/AbTG2yC4KjNRxe.../elements"
  }
}
```

---

## Operações de Busca

### Busca de PI Points
```
GET http://10.247.224.39/piwebapi/points/{dataServerWebId}/search
  ?query=tag:sin* AND PointType:Float64
```

| Sintaxe de Consulta | Descrição |
|----------------------|-----------|
| `tag:=sin*` | Nome do PI Point com curinga |
| `PointType:Float64` | Filtro por tipo de dado |
| `PointSource:L` | Filtro por origem do point |
| `Value:>100` | Filtro por valor atual |
| `AND`, `OR` | Operadores lógicos |

### Busca de AF Elements
```
GET http://10.247.224.39/piwebapi/assetdatabases/{webId}/elements
  ?searchQuery=Name:=Pump* Template:Centrifugal
```

### Busca de AF Attributes
```
GET http://10.247.224.39/piwebapi/assetdatabases/{webId}/attributes
  ?searchQuery=Name:=Temperature*
```

---

## Informações do Sistema

### Raiz da API (Descobre Todos os Links)
```
GET http://10.247.224.39/piwebapi/
```

### Status do Servidor
```
GET http://10.247.224.39/piwebapi/system/status
```

### Informações do Usuário Atual
```
GET http://10.247.224.39/piwebapi/system/userinfo
```

### Listar Data Servers
```
GET http://10.247.224.39/piwebapi/dataservers
```

### Obter Points de um Data Server
```
GET http://10.247.224.39/piwebapi/dataservers/{webId}/points
```

---

## Tratamento de Erros

### Códigos de Status
| Código | Significado | Ação |
|--------|-------------|------|
| 200 | Sucesso | Processar resposta |
| 400 | Requisição Inválida | Verificar parâmetros |
| 401 | Não Autorizado | Verificar credenciais |
| 403 | Proibido | Verificar permissões |
| 404 | Não Encontrado | Verificar caminho/WebId |
| 500 | Erro do Servidor | Tentar novamente depois |

### Erros em Valores de Stream
Valores individuais podem conter erros enquanto a requisição como um todo é bem-sucedida:
```json
{
  "Timestamp": "2024-01-01T00:00:00Z",
  "Value": null,
  "Good": false,
  "Errors": [
    {
      "FieldName": "Value",
      "Message": ["PI Point not found."]
    }
  ]
}
```

---

## Padrões Comuns

### Obter Valor Atual de um PI Point
```bash
# Passo 1: Obter WebId a partir do caminho
WEBID=$(curl -s "http://10.247.224.39/piwebapi/points?path=\\PIMS\sinusoid" | jq -r '.WebId')

# Passo 2: Obter valor atual
curl -s "http://10.247.224.39/piwebapi/streams/$WEBID/value"
```

### Obter Dados Históricos de um PI Point
```bash
WEBID=$(curl -s "http://10.247.224.39/piwebapi/points?path=\\PIMS\sinusoid" | jq -r '.WebId')
curl -s "http://10.247.224.39/piwebapi/streams/$WEBID/recorded?startTime=-7d&endTime=*&maxCount=500"
```

### Obter Médias Horárias das Últimas 24h
```bash
WEBID=$(curl -s "http://10.247.224.39/piwebapi/points?path=\\PIMS\sinusoid" | jq -r '.WebId')
curl -s "http://10.247.224.39/piwebapi/streams/$WEBID/summary?startTime=-1d&endTime=*&summaryType=Average&duration=1h"
```

### Obter Todos os Attributes de um Element
```bash
ELEMENT_WEBID=$(curl -s "http://10.247.224.39/piwebapi/elements?path=\\PIMS\MyDB\Pump1" | jq -r '.WebId')
curl -s "http://10.247.224.39/piwebapi/elements/$ELEMENT_WEBID/attributes"
```

### Obter Valores Atuais de Múltiplos Points
```bash
# Usando stream set ad-hoc
WEBID1=$(curl -s "http://10.247.224.39/piwebapi/points?path=\\PIMS\sinusoid" | jq -r '.WebId')
WEBID2=$(curl -s "http://10.247.224.39/piwebapi/points?path=\\PIMS\cdt158" | jq -r '.WebId')
curl -s "http://10.247.224.39/piwebapi/streamsets/value?webId=$WEBID1&webId=$WEBID2"
```

### Encontrar Event Frames Ativos
```bash
curl -s "http://10.247.224.39/piwebapi/assetdatabases/{dbWebId}/eventframes?searchQuery=InProgress:true"
```

### Exportar Estrutura do Database como XML
```
GET http://10.247.224.39/piwebapi/assetdatabases/{webId}/export?mode=Default
```

### Cálculo de Performance Equation
```
GET http://10.247.224.39/piwebapi/calculations
  ?expression='sinusoid'*2
  &startTime=-1h
  &endTime=*
  &interval=1m
```

---

## Referência Rápida: Seleção de Endpoint

| Necessidade | Endpoint |
|-------------|----------|
| Valor atual | `GET /streams/{webId}/value` |
| Dados históricos brutos | `GET /streams/{webId}/recorded` |
| Dados com preenchimento de lacunas | `GET /streams/{webId}/interpolated` |
| Estatísticas agregadas | `GET /streams/{webId}/summary` |
| Dados para gráfico | `GET /streams/{webId}/plot` |
| Múltiplos streams | Endpoints `/streamsets/...` |
| Encontrar PI Point | `GET /points?path=\\...` |
| Encontrar Element | `GET /elements?path=\\...` |
| Encontrar Attribute | `GET /attributes?path=\\...` |
| Listar elements no DB | `GET /assetdatabases/{webId}/elements` |
| Attributes de um element | `GET /elements/{webId}/attributes` |
| Event frames | `GET /elements/{webId}/eventframes` |
| Buscar points | `GET /points/{webId}/search?query=...` |
| Info do servidor | `GET /system/status` |

---

## Strings de Tempo

| Formato | Significado |
|---------|-------------|
| `*` | Agora |
| `*-1h` | 1 hora atrás |
| `*-1d` | 1 dia atrás |
| `*-7d` | 7 dias atrás |
| `T` | Hoje à meia-noite |
| `Y` | Ontem à meia-noite |
| `Monday` | Segunda-feira mais recente à meia-noite |
| `2024-01-01T00:00:00Z` | Hora UTC absoluta |
| `2024-01-01T00:00:00-05:00` | Com offset de fuso horário |

**Intervalos Padrão**: `ms`, `s`, `m`, `h`, `d`, `mo`, `w`, `wd`, `yd`

---

## Codificação de URL

Caracteres especiais em caminhos PI devem ser codificados por cento (percent-encoded):

| Caracter | Codificação |
|----------|-------------|
| `\` | `%5C` |
| `|` | `%7C` |
| `#` | `%23` |
| Espaço | `%20` |
| `:` | `%3A` |

---

## Tipos de WebID

WebIDs identificam objetos PI/AF. O primeiro caractere indica o tipo:

| Tipo | 1º Caractere | Descrição |
|------|-------------|-----------|
| Full | `F` | Identificador completo (recomendado) |
| ID Only | `I` | Baseado em GUID |
| Path Only | `P` | Baseado em caminho |
| Local ID | `L` | GUID local |
| Default | `D` | Identificador padrão |

---

## Servidor

`http://10.247.224.39/piwebapi`
