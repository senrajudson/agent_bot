# PI Web API - Guia Operacional para Agente RAG

Documento feito para agentes de IA que consultam tags no PI System via PI Web API.

Objetivo: ensinar o agente a consultar valores atuais, históricos, metadados, unidades de engenharia, descriptor, tipo da tag, instrumenttag, location, digital set e digital states.

Este documento deve ser dividido em chunks pequenos por intenção de consulta. Cada seção abaixo foi escrita para funcionar como um documento recuperável independente em um RAG com top-k baixo.

Base da API:

```text
http://10.247.224.39/piwebapi
```

Servidor PI Data Archive padrão:

```text
PIMS
```

Formato padrão de path de uma tag:

```text
\\PIMS\NOME_DA_TAG
```

Exemplo real:

```text
\\PIMS\LFI_RB3_VAZ_GN_TOTAL
```

Endpoint para encontrar uma tag pelo nome exato:

```text
GET /points?path=\\PIMS\NOME_DA_TAG
```

Exemplo:

```text
GET http://10.247.224.39/piwebapi/points?path=\\PIMS\LFI_RB3_VAZ_GN_TOTAL
```

---

# CHUNK 01 - Fluxo base: tag para WebId

## Intenção

Use este chunk quando o usuário perguntar sobre:

* valor atual de uma tag
* último valor
* snapshot
* valor agora
* histórico de uma tag
* média, máximo, mínimo ou soma
* dados interpolados
* dados gravados
* qualquer consulta de série temporal

## Regra principal

A PI Web API não consulta o stream diretamente pelo nome da tag. Primeiro é necessário buscar o `WebId` da tag.

Fluxo padrão:

```text
1. Receber o nome da tag do usuário.
2. Montar o path: \\PIMS\NOME_DA_TAG
3. Consultar: GET /points?path=\\PIMS\NOME_DA_TAG
4. Extrair o campo WebId.
5. Usar o WebId nos endpoints /streams/{webId}/...
```

## Request para obter WebId

```http
GET http://10.247.224.39/piwebapi/points?path=\\PIMS\LFI_RB3_VAZ_GN_TOTAL
```

## Resposta esperada

```json
{
  "WebId": "F1DPxhF1MCtATE6DjgaMSVY2gghOAAAAUE1NU1xMRklfUkIzX1ZBWl9HTl9UT1RBTA",
  "Id": 57476,
  "Name": "LFI_RB3_VAZ_GN_TOTAL",
  "Path": "\\\\pims\\LFI_RB3_VAZ_GN_TOTAL",
  "Descriptor": "VAZÃO DE GN TOTAL DO RB3",
  "PointClass": "classic",
  "PointType": "Float32",
  "DigitalSetName": "",
  "EngineeringUnits": "Nm3/h",
  "Span": 12000.0,
  "Zero": 0.0,
  "Step": false,
  "Future": false,
  "DisplayDigits": 2,
  "Links": {
    "Self": "http://10.247.224.39/piwebapi/points/{webId}",
    "DataServer": "http://10.247.224.39/piwebapi/dataservers/{dataServerWebId}",
    "Attributes": "http://10.247.224.39/piwebapi/points/{webId}/attributes",
    "InterpolatedData": "http://10.247.224.39/piwebapi/streams/{webId}/interpolated",
    "RecordedData": "http://10.247.224.39/piwebapi/streams/{webId}/recorded",
    "PlotData": "http://10.247.224.39/piwebapi/streams/{webId}/plot",
    "SummaryData": "http://10.247.224.39/piwebapi/streams/{webId}/summary",
    "Value": "http://10.247.224.39/piwebapi/streams/{webId}/value",
    "EndValue": "http://10.247.224.39/piwebapi/streams/{webId}/end"
  }
}
```

## Campos mais importantes

```text
WebId            Identificador necessário para consultar /streams
Name             Nome da tag
Path             Caminho completo no PI
Descriptor       Descrição da tag
PointType        Tipo de dado da tag
DigitalSetName   Nome do digital set, quando for tag digital
EngineeringUnits Unidade de engenharia
Span             Faixa máxima configurada
Zero             Zero configurado
Step             true para comportamento discreto/degrau
Links.Value      Link direto para valor atual
Links.Attributes Link direto para atributos do PI Point
```

## Regra para o agente

Depois de obter o `WebId`, prefira usar os links retornados em `Links` quando estiverem disponíveis.

Exemplo:

```text
Links.Value -> consultar valor atual
Links.RecordedData -> consultar histórico bruto
Links.InterpolatedData -> consultar interpolados
Links.SummaryData -> consultar resumos estatísticos
Links.Attributes -> consultar atributos do point
```

---

# CHUNK 02 - Valor atual de uma tag

## Intenção

Use este chunk quando o usuário perguntar:

* qual o valor atual da tag
* último valor
* valor agora
* snapshot
* quanto está a tag
* status atual
* ler tag em tempo real

## Fluxo

```text
1. Buscar o PI Point pelo path.
2. Extrair WebId.
3. Consultar /streams/{webId}/value.
4. Interpretar Timestamp, Value, Good e Questionable.
5. Responder com valor, unidade, timestamp e qualidade.
```

## Request 1 - obter WebId

```http
GET http://10.247.224.39/piwebapi/points?path=\\PIMS\LFI_RB3_VAZ_GN_TOTAL
```

## Request 2 - obter valor atual

```http
GET http://10.247.224.39/piwebapi/streams/{webId}/value
```

Exemplo com WebId:

```http
GET http://10.247.224.39/piwebapi/streams/F1DPxhF1MCtATE6DjgaMSVY2gghOAAAAUE1NU1xMRklfUkIzX1ZBWl9HTl9UT1RBTA/value
```

## Resposta típica

```json
{
  "Timestamp": "2026-06-15T13:10:00Z",
  "Value": 4382.45,
  "UnitsAbbreviation": "Nm3/h",
  "Good": true,
  "Questionable": false,
  "Substituted": false
}
```

## Como interpretar

```text
Timestamp          Data/hora do valor
Value              Valor retornado
UnitsAbbreviation  Unidade, quando disponível
Good               true significa valor válido
Questionable       true significa valor suspeito
Substituted        true significa valor substituído
```

## Resposta ideal do agente

```text
A tag LFI_RB3_VAZ_GN_TOTAL está com valor atual de 4382,45 Nm3/h em 15/06/2026 10:10:00.
Qualidade: boa.
```

## Regras de qualidade

Se `Good = false`, não trate o valor como valor confiável.

Responder assim:

```text
A tag retornou valor inválido ou ruim no PI.
Timestamp: ...
Valor retornado: ...
Good: false
```

Se `Questionable = true`, avisar que o valor está questionável.

Se `Value` vier como objeto, verificar campos internos como `Name`, `Value` ou `IsSystem`.

---

# CHUNK 03 - Metadados da tag: unidade, descriptor, tipo, span e step

## Intenção

Use este chunk quando o usuário perguntar:

* qual a unidade da tag
* engunits
* engineering units
* descriptor
* descrição da tag
* tipo da tag
* pointtype
* span
* zero
* step
* display digits
* classe do point
* metadados da tag

## Endpoint principal

Para a maioria dos metadados básicos, basta consultar o PI Point pelo path:

```http
GET http://10.247.224.39/piwebapi/points?path=\\PIMS\NOME_DA_TAG
```

Exemplo:

```http
GET http://10.247.224.39/piwebapi/points?path=\\PIMS\LFI_RB3_VAZ_GN_TOTAL
```

## Campos retornados no PI Point

```text
Name              Nome da tag
Path              Caminho completo
Descriptor        Descrição da tag
PointClass        Classe do point
PointType         Tipo de dado
DigitalSetName    Nome do digital set
EngineeringUnits  Unidade de engenharia
Span              Faixa máxima
Zero              Zero configurado
Step              Indica se é tag discreta/degrau
Future            Indica se é future data
DisplayDigits     Casas/dígitos para exibição
Links.Attributes  Link para atributos adicionais
```

## Exemplo de resposta

```json
{
  "Name": "LFI_RB3_VAZ_GN_TOTAL",
  "Descriptor": "VAZÃO DE GN TOTAL DO RB3",
  "PointType": "Float32",
  "DigitalSetName": "",
  "EngineeringUnits": "Nm3/h",
  "Span": 12000.0,
  "Zero": 0.0,
  "Step": false,
  "DisplayDigits": 2
}
```

## Resposta ideal do agente

```text
Metadados da tag LFI_RB3_VAZ_GN_TOTAL:

Descrição: VAZÃO DE GN TOTAL DO RB3
Tipo: Float32
Unidade: Nm3/h
Span: 12000
Zero: 0
Step: false
DigitalSetName: vazio, portanto não parece ser uma tag digital.
```

## Quando usar selectedFields

Use `selectedFields` para reduzir a resposta:

```http
GET http://10.247.224.39/piwebapi/points?path=\\PIMS\LFI_RB3_VAZ_GN_TOTAL&selectedFields=WebId;Name;Descriptor;PointType;DigitalSetName;EngineeringUnits;Span;Zero;Step;DisplayDigits;Links
```

## Atenção

Em alguns ambientes, o nome do campo de digital set pode aparecer como:

```text
DigitalSetName
```

Não assumir que sempre será:

```text
DigitalSet
```

No ambiente atual, a resposta do navegador mostrou `DigitalSetName`.

---

# CHUNK 04 - Atributos do PI Point: instrumenttag, location e atributos clássicos

## Intenção

Use este chunk quando o usuário perguntar:

* instrumenttag
* tag do instrumento
* engunits como atributo
* location1
* location2
* location3
* location4
* location5
* pointsource
* pointid
* atributos do point
* atributos clássicos da tag

## Regra

Alguns metadados vêm diretamente em `/points?path=...`.

Outros atributos devem ser buscados em:

```http
GET /points/{webId}/attributes
```

Ou pelo link retornado no PI Point:

```text
Links.Attributes
```

## Fluxo

```text
1. Buscar o PI Point pelo path.
2. Extrair WebId.
3. Consultar /points/{webId}/attributes.
4. Filtrar o atributo desejado pelo nome.
```

## Request 1 - obter WebId

```http
GET http://10.247.224.39/piwebapi/points?path=\\PIMS\NOME_DA_TAG
```

## Request 2 - listar atributos do point

```http
GET http://10.247.224.39/piwebapi/points/{webId}/attributes
```

## Request para um atributo específico

```http
GET http://10.247.224.39/piwebapi/points/{webId}/attributes?name=instrumenttag
```

Exemplos:

```http
GET http://10.247.224.39/piwebapi/points/{webId}/attributes?name=instrumenttag
```

```http
GET http://10.247.224.39/piwebapi/points/{webId}/attributes?name=location1
```

```http
GET http://10.247.224.39/piwebapi/points/{webId}/attributes?name=location2
```

```http
GET http://10.247.224.39/piwebapi/points/{webId}/attributes?name=engunits
```

## Exemplo de resposta

```json
{
  "Items": [
    {
      "Name": "instrumenttag",
      "Value": "FT-101"
    }
  ]
}
```

## Resposta ideal do agente

```text
O instrumenttag da tag LFI_RB3_VAZ_GN_TOTAL é FT-101.
```

## Regra de fallback

Se o atributo não existir ou vier vazio:

```text
Não encontrei valor preenchido para instrumenttag nessa tag.
```

Não inventar valor.

---

# CHUNK 05 - DigitalSetName e Digital States

## Intenção

Use este chunk quando o usuário perguntar:

* digital states
* digital set
* estados digitais
* estados possíveis da tag
* valor 0 significa o quê
* valor 1 significa o quê
* ligado/desligado
* aberto/fechado
* status de tag digital
* tag digital

## Como identificar tag digital

Consultar o PI Point:

```http
GET http://10.247.224.39/piwebapi/points?path=\\PIMS\NOME_DA_TAG
```

Verificar:

```text
PointType
DigitalSetName
Step
```

Uma tag digital normalmente tem:

```text
PointType = Digital
DigitalSetName preenchido
Step = true
```

Mas nem todo status discreto necessariamente será `PointType = Digital`. Também pode haver status representado como inteiro.

## Exemplo de tag não digital

```json
{
  "Name": "LFI_RB3_VAZ_GN_TOTAL",
  "PointType": "Float32",
  "DigitalSetName": "",
  "EngineeringUnits": "Nm3/h",
  "Step": false
}
```

Neste caso, não consultar Digital States, porque `DigitalSetName` está vazio.

## Fluxo para obter estados digitais

```text
1. Buscar a tag em /points?path=\\PIMS\TAG.
2. Ler DigitalSetName.
3. Se DigitalSetName estiver vazio, informar que a tag não possui digital set.
4. Se DigitalSetName estiver preenchido, buscar o DataServer.
5. Listar os enumeration sets do DataServer.
6. Encontrar o enumeration set com o mesmo nome de DigitalSetName.
7. Consultar enumerationvalues.
```

## Request 1 - buscar PI Point

```http
GET http://10.247.224.39/piwebapi/points?path=\\PIMS\NOME_DA_TAG
```

## Request 2 - listar Data Servers

```http
GET http://10.247.224.39/piwebapi/dataservers
```

Encontrar o item com:

```text
Name = PIMS
```

Extrair:

```text
WebId
```

## Request 3 - listar Digital Sets do servidor

```http
GET http://10.247.224.39/piwebapi/dataservers/{dataServerWebId}/enumerationsets
```

Encontrar o item com:

```text
Name = DigitalSetName da tag
```

Extrair:

```text
WebId do enumeration set
```

## Request 4 - listar estados do Digital Set

```http
GET http://10.247.224.39/piwebapi/enumerationsets/{enumSetWebId}/enumerationvalues
```

## Exemplo de resposta

```json
{
  "Items": [
    {
      "Value": 0,
      "Name": "Desligado",
      "Description": "Equipamento desligado"
    },
    {
      "Value": 1,
      "Name": "Ligado",
      "Description": "Equipamento ligado"
    }
  ]
}
```

## Como interpretar valor atual de tag digital

Ao consultar:

```http
GET /streams/{webId}/value
```

O campo `Value` pode vir de duas formas.

Forma 1: número simples:

```json
{
  "Value": 1,
  "Good": true
}
```

Neste caso, usar o Digital Set para mapear:

```text
1 -> Ligado
```

Forma 2: objeto:

```json
{
  "Value": {
    "Name": "Ligado",
    "Value": 1,
    "IsSystem": false
  },
  "Good": true
}
```

Neste caso, usar diretamente `Value.Name` e `Value.Value`.

## Resposta ideal do agente

```text
A tag CPD_LP_SECADOR_STATUS usa o digital set SECADOR_STATUS.

Estados possíveis:
0 - Desligado
1 - Ligado
2 - Manutenção
```

## Se a tag não tiver DigitalSetName

Responder:

```text
A tag LFI_RB3_VAZ_GN_TOTAL não possui DigitalSetName preenchido. Ela é do tipo Float32, então não parece ser uma tag digital.
```

---

# CHUNK 06 - Histórico bruto: recorded values

## Intenção

Use este chunk quando o usuário perguntar:

* histórico da tag
* valores gravados
* recorded
* eventos gravados
* últimos valores
* valores dos últimos minutos
* valores das últimas horas
* amostras reais gravadas

## Endpoint

```http
GET /streams/{webId}/recorded
```

## Fluxo

```text
1. Buscar WebId em /points?path=\\PIMS\TAG.
2. Consultar /streams/{webId}/recorded.
3. Usar startTime, endTime e maxCount.
4. Retornar os valores com Timestamp, Value e qualidade.
```

## Request

```http
GET http://10.247.224.39/piwebapi/streams/{webId}/recorded?startTime=-1d&endTime=*&maxCount=1000
```

## Parâmetros principais

```text
startTime      Início do intervalo
endTime        Fim do intervalo
maxCount       Máximo de eventos retornados
boundaryType   Inside, Outside ou Interpolated
retrievalMode  Auto, AtOrBefore, Before, AtOrAfter, After, Exact
```

## Exemplos de tempo

```text
*                 agora
*-1h              uma hora atrás
*-1d              um dia atrás
2026-06-01T00:00:00Z
2026-06-01T00:00:00-03:00
```

## Exemplo

```http
GET http://10.247.224.39/piwebapi/streams/{webId}/recorded?startTime=*-8h&endTime=*&maxCount=500
```

## Resposta típica

```json
{
  "Items": [
    {
      "Timestamp": "2026-06-15T10:00:00Z",
      "Value": 4312.4,
      "Good": true,
      "Questionable": false
    },
    {
      "Timestamp": "2026-06-15T10:05:00Z",
      "Value": 4330.1,
      "Good": true,
      "Questionable": false
    }
  ]
}
```

## Quando usar recorded

Use `recorded` quando o usuário quiser os valores reais armazenados no PI, sem interpolação.

Não usar `recorded` para “valor a cada 1 minuto” se a tag não grava a cada 1 minuto. Para intervalo fixo, usar `interpolated`.

---

# CHUNK 07 - Valores interpolados

## Intenção

Use este chunk quando o usuário perguntar:

* valor a cada 1 minuto
* valor de 5 em 5 minutos
* série regular
* interpolado
* preencher lacunas
* amostragem fixa
* histórico com intervalo fixo

## Endpoint

```http
GET /streams/{webId}/interpolated
```

## Fluxo

```text
1. Buscar WebId em /points?path=\\PIMS\TAG.
2. Consultar /streams/{webId}/interpolated.
3. Informar startTime, endTime e interval.
4. Retornar série com timestamps regulares.
```

## Request

```http
GET http://10.247.224.39/piwebapi/streams/{webId}/interpolated?startTime=-1d&endTime=*&interval=1h
```

## Parâmetros principais

```text
startTime   Início do intervalo
endTime     Fim do intervalo
interval    Espaçamento entre valores
syncTime    Hora âncora para alinhamento do intervalo
```

## Exemplos de interval

```text
1m
5m
15m
30m
1h
1d
```

## Exemplo

```http
GET http://10.247.224.39/piwebapi/streams/{webId}/interpolated?startTime=*-8h&endTime=*&interval=5m
```

## Quando usar interpolated

Use quando o usuário pedir dados em uma frequência fixa.

Exemplo:

```text
Me traga a temperatura de 10 em 10 minutos nas últimas 6 horas.
```

Não usar interpolated quando o usuário pedir “eventos reais gravados”. Nesse caso, usar `recorded`.

---

# CHUNK 08 - Summary: média, mínimo, máximo, total e percent good

## Intenção

Use este chunk quando o usuário perguntar:

* média
* máximo
* mínimo
* soma
* total
* desvio padrão
* percent good
* estatística
* agregação
* média horária
* média diária
* resumo da tag

## Endpoint

```http
GET /streams/{webId}/summary
```

## Fluxo

```text
1. Buscar WebId em /points?path=\\PIMS\TAG.
2. Consultar /streams/{webId}/summary.
3. Definir startTime e endTime.
4. Definir summaryType.
5. Definir summaryDuration quando quiser janelas, por exemplo médias horárias.
6. Definir calculationBasis.
```

## Request simples

```http
GET http://10.247.224.39/piwebapi/streams/{webId}/summary?startTime=-1d&endTime=*&summaryType=Average
```

## Request com médias horárias

```http
GET http://10.247.224.39/piwebapi/streams/{webId}/summary?startTime=-1d&endTime=*&summaryType=Average&summaryDuration=1h&calculationBasis=TimeWeighted
```

## summaryType comuns

```text
Average       Média
Minimum       Mínimo
Maximum       Máximo
Range         Máximo - mínimo
StdDev        Desvio padrão
Count         Contagem
PercentGood   Percentual de dados bons
Total         Totalização
All           Todos os resumos disponíveis
```

## calculationBasis

```text
TimeWeighted   Ponderado pelo tempo. Usar para temperatura, pressão, vazão, nível e variáveis contínuas.
EventWeighted  Cada evento tem o mesmo peso. Usar quando cada amostra gravada deve ter peso igual.
```

## summaryDuration

Use `summaryDuration` quando quiser dividir o período em blocos.

Exemplos:

```text
summaryDuration=1h    médias horárias
summaryDuration=1d    médias diárias
summaryDuration=15m   médias de 15 minutos
```

## Exemplo de resposta

```json
{
  "Items": [
    {
      "Type": "Average",
      "Value": {
        "Timestamp": "2026-06-15T10:00:00Z",
        "Value": 4320.5,
        "Good": true
      }
    }
  ]
}
```

## Regra de qualidade

Se o item retornado tiver `Good = false`, não usar o valor como confiável.

Se o usuário pedir estatística e houver itens ruins, informar a quantidade de itens ignorados ou sinalizar que a qualidade do cálculo pode estar comprometida.

---

# CHUNK 09 - Consumo de vazão em Nm3 usando médias horárias

## Intenção

Use este chunk quando o usuário perguntar:

* consumo de gás
* consumo total
* total de vazão
* somar vazão
* consumo mensal
* consumo diário
* consumo no período
* Nm3 a partir de Nm3/h

## Contexto

Para uma tag de vazão em `Nm3/h`, o consumo em `Nm3` pode ser calculado usando médias horárias.

Regra operacional:

```text
1. Consultar médias horárias da vazão com summaryType=Average.
2. Usar summaryDuration=1h.
3. Usar calculationBasis=TimeWeighted.
4. Somar os valores médios horários no cliente/agente.
5. Como cada média representa 1 hora, cada média em Nm3/h equivale a Nm3 no bloco de 1 hora.
```

## Endpoint

```http
GET /streams/{webId}/summary
```

## Exemplo para consumo mensal

```http
GET http://10.247.224.39/piwebapi/streams/{webId}/summary?startTime=2026-05-01T00:00:00-03:00&endTime=2026-06-01T00:00:00-03:00&summaryType=Average&summaryDuration=1h&calculationBasis=TimeWeighted
```

## Cálculo no agente

Para cada item retornado:

```text
Se Good = true:
    consumo_total += Value.Value
Se Good = false:
    ignorar ou sinalizar item ruim
```

## Exemplo conceitual

```text
Hora 01: média = 100 Nm3/h
Hora 02: média = 120 Nm3/h
Hora 03: média = 130 Nm3/h

Consumo = 100 + 120 + 130 = 350 Nm3
```

## Resposta ideal do agente

```text
O consumo estimado no período foi de 350 Nm3, calculado pela soma das médias horárias TimeWeighted da tag de vazão.
```

## Atenção

A chamada `/summary` retorna os blocos de média. Ela não soma automaticamente todos os blocos horários. A soma final deve ser feita pelo agente ou pela aplicação cliente.

---

# CHUNK 10 - Múltiplas tags: streamsets e batch

## Intenção

Use este chunk quando o usuário perguntar:

* valor atual de várias tags
* consultar múltiplas tags
* pegar metadados e valores juntos
* otimizar várias consultas
* reduzir chamadas HTTP
* batch
* streamsets

## Opção 1 - streamsets ad-hoc para valor atual de múltiplos WebIds

Use quando já tiver os WebIds e quiser o valor atual de várias tags.

```http
GET http://10.247.224.39/piwebapi/streamsets/value?webId={webId1}&webId={webId2}
```

Exemplo:

```http
GET http://10.247.224.39/piwebapi/streamsets/value?webId=WEBID_1&webId=WEBID_2&webId=WEBID_3
```

## Opção 2 - batch para buscar WebId e valor na mesma chamada

Use quando o agente recebeu nomes de tags e precisa buscar WebId + valor atual.

```http
POST http://10.247.224.39/piwebapi/batch
Content-Type: application/json
```

Exemplo:

```json
{
  "point_0": {
    "Method": "GET",
    "Resource": "http://10.247.224.39/piwebapi/points?path=\\PIMS\LFI_RB3_VAZ_GN_TOTAL"
  },
  "value_0": {
    "Method": "GET",
    "ParentIds": ["point_0"],
    "Parameters": ["$.point_0.Content.WebId"],
    "Resource": "http://10.247.224.39/piwebapi/streams/{0}/value"
  },
  "point_1": {
    "Method": "GET",
    "Resource": "http://10.247.224.39/piwebapi/points?path=\\PIMS\SINUSOID"
  },
  "value_1": {
    "Method": "GET",
    "ParentIds": ["point_1"],
    "Parameters": ["$.point_1.Content.WebId"],
    "Resource": "http://10.247.224.39/piwebapi/streams/{0}/value"
  }
}
```

## Resposta típica do batch

```json
{
  "point_0": {
    "Status": 200,
    "Content": {
      "WebId": "..."
    }
  },
  "value_0": {
    "Status": 200,
    "Content": {
      "Timestamp": "2026-06-15T10:00:00Z",
      "Value": 4382.45,
      "Good": true
    }
  }
}
```

## Regra para o agente

Para poucas tags, pode usar chamadas simples.

Para muitas tags, preferir batch ou streamsets.

Se o batch retornar status diferente de 200 em algum item, tratar aquele item individualmente e não falhar toda a resposta.

---

# CHUNK 11 - Buscar tag quando o nome não é exato

## Intenção

Use este chunk quando o usuário perguntar:

* procurar tag
* buscar tags parecidas
* não sei o nome completo
* tags que começam com
* tags que contêm
* listar tags
* encontrar tag por parte do nome

## Regra

Se o usuário informou o nome exato da tag, usar:

```http
GET /points?path=\\PIMS\NOME_DA_TAG
```

Se o usuário informou apenas parte do nome, usar busca de points.

## Fluxo

```text
1. Obter o DataServer WebId do servidor PIMS.
2. Buscar points no DataServer.
3. Retornar lista curta de candidatos.
4. Se houver muitas opções, pedir para o usuário escolher.
```

## Request 1 - listar dataservers

```http
GET http://10.247.224.39/piwebapi/dataservers
```

Encontrar:

```text
Name = PIMS
```

Extrair:

```text
WebId
```

## Request 2 - buscar points no DataServer

```http
GET http://10.247.224.39/piwebapi/dataservers/{dataServerWebId}/points?nameFilter=*VAZ_GN*
```

## Exemplos de filtros

```text
*VAZ_GN*
LFI_RB3*
*TEMP*
*PRESS*
```

## Resposta ideal do agente

```text
Encontrei algumas tags parecidas:

1. LFI_RB3_VAZ_GN_TOTAL - VAZÃO DE GN TOTAL DO RB3
2. LFI_RB3_VAZ_GN_FORNO - VAZÃO DE GN DO FORNO
3. LFI_RB3_VAZ_GN_ZONA1 - VAZÃO DE GN ZONA 1

Qual delas você quer consultar?
```

## Regra importante

Não escolher uma tag automaticamente se houver ambiguidade forte.

---

# CHUNK 12 - Tratamento de erros e qualidade

## Intenção

Use este chunk quando ocorrer:

* tag não encontrada
* WebId inválido
* erro 400
* erro 401
* erro 403
* erro 404
* erro 500
* Good false
* Questionable true
* valor bad
* No Data
* Calc Failed
* Timeout

## Status HTTP

```text
200  Sucesso
400  Requisição inválida
401  Não autorizado
403  Sem permissão
404  Objeto não encontrado
500  Erro interno do servidor
```

## Erro 404 ao buscar point

Se:

```http
GET /points?path=\\PIMS\TAG
```

retornar 404, responder:

```text
Não encontrei a tag TAG no servidor PIMS. Verifique se o nome está correto.
```

## Erro 401 ou 403

Responder:

```text
A API recusou a consulta por autenticação ou permissão. O usuário usado pela aplicação pode não ter acesso a essa tag ou endpoint.
```

## Valor com Good false

Exemplo:

```json
{
  "Timestamp": "2026-06-15T10:00:00Z",
  "Value": null,
  "Good": false,
  "Questionable": false
}
```

Resposta:

```text
A tag retornou dado ruim no PI. Não vou considerar esse valor como confiável.
Timestamp: ...
Good: false
```

## Valor Questionable

Se:

```json
{
  "Good": true,
  "Questionable": true
}
```

Responder:

```text
A tag retornou valor, mas a qualidade está questionável.
```

## Regra geral

Não ocultar qualidade ruim.

Não inventar valor quando `Value` vier nulo.

Não transformar `Good=false` em zero.

Não transformar erro de API em valor zero.

---

# CHUNK 13 - Strings de tempo e timezone

## Intenção

Use este chunk quando o usuário pedir:

* últimas 24 horas
* hoje
* ontem
* mês passado
* desde meia-noite
* período específico
* data inicial e final
* turno
* intervalo de tempo

## Strings PI comuns

```text
*       agora
*-1h    uma hora atrás
*-8h    oito horas atrás
*-1d    um dia atrás
T       hoje à meia-noite
Y       ontem à meia-noite
```

## Datas absolutas

Preferir usar ISO 8601 com offset quando o usuário falar em horário local do Brasil:

```text
2026-06-15T00:00:00-03:00
2026-06-15T23:59:59-03:00
```

## Exemplo: hoje

```http
GET /streams/{webId}/recorded?startTime=2026-06-15T00:00:00-03:00&endTime=2026-06-15T23:59:59-03:00
```

## Exemplo: últimas 8 horas

```http
GET /streams/{webId}/recorded?startTime=*-8h&endTime=*
```

## Exemplo: mês de maio de 2026

```text
startTime=2026-05-01T00:00:00-03:00
endTime=2026-06-01T00:00:00-03:00
```

## Regra para o agente

Quando o usuário pedir “mês passado”, calcular o primeiro dia do mês anterior até o primeiro dia do mês atual.

Não usar dia 30 ou 31 manualmente se o mês puder variar.

---

# CHUNK 14 - Codificação de URL

## Intenção

Use este chunk quando a URL falhar por caracteres especiais ou quando for necessário montar path de PI Point, AF Attribute ou Element.

## Caracteres importantes

```text
\   pode precisar ser codificado como %5C
|   pode precisar ser codificado como %7C
#   pode precisar ser codificado como %23
espaço pode precisar ser codificado como %20
:   pode precisar ser codificado como %3A
```

## Path normal em exemplos

```text
\\PIMS\LFI_RB3_VAZ_GN_TOTAL
```

## URL com path direto

```http
GET http://10.247.224.39/piwebapi/points?path=\\PIMS\LFI_RB3_VAZ_GN_TOTAL
```

## URL percent-encoded equivalente

```http
GET http://10.247.224.39/piwebapi/points?path=%5C%5CPIMS%5CLFI_RB3_VAZ_GN_TOTAL
```

## Regra para o agente

Se estiver usando biblioteca HTTP, passar `path` como parâmetro de query e deixar a biblioteca codificar.

Em Python com requests:

```python
import requests

base_url = "http://10.247.224.39/piwebapi"
tag = "LFI_RB3_VAZ_GN_TOTAL"

response = requests.get(
    f"{base_url}/points",
    params={"path": f"\\\\PIMS\\{tag}"},
    timeout=30,
)
response.raise_for_status()
point = response.json()
```

---

# CHUNK 15 - Respostas finais do agente

## Intenção

Use este chunk para padronizar a forma como o agente responde ao usuário.

## Valor atual

Formato:

```text
Tag: NOME_DA_TAG
Valor: VALOR UNIDADE
Timestamp: DATA/HORA
Qualidade: boa/questionável/ruim
```

Exemplo:

```text
Tag: LFI_RB3_VAZ_GN_TOTAL
Valor: 4382,45 Nm3/h
Timestamp: 15/06/2026 10:10:00
Qualidade: boa
```

## Metadados

Formato:

```text
Tag: NOME_DA_TAG
Descrição: DESCRIPTOR
Tipo: POINTTYPE
Unidade: ENGINEERINGUNITS
DigitalSetName: DIGITALSETNAME
Span: SPAN
Zero: ZERO
Step: STEP
```

## Digital states

Formato:

```text
Tag: NOME_DA_TAG
DigitalSetName: NOME_DO_SET

Estados:
0 - Desligado
1 - Ligado
2 - Manutenção
```

## Histórico

Para poucos valores, pode listar em tabela.

Para muitos valores, resumir:

```text
Foram encontrados 500 eventos no período.
Primeiro valor: ...
Último valor: ...
Menor valor: ...
Maior valor: ...
```

## Erros

Tag não encontrada:

```text
Não encontrei a tag NOME_DA_TAG no servidor PIMS.
```

Sem permissão:

```text
A consulta foi recusada por permissão ou autenticação.
```

Dado ruim:

```text
A tag retornou dado ruim no PI. Não vou considerar esse valor como confiável.
```

## Regra final

Sempre que possível, responder com:

```text
valor + unidade + timestamp + qualidade
```

Nunca responder apenas o número sem contexto.

---

# CHUNK 16 - Decisão rápida de endpoint

## Intenção

Use este chunk quando o agente precisa escolher rapidamente qual endpoint usar.

## Tabela de decisão

```text
Usuário pediu valor atual:
    /points?path=... -> /streams/{webId}/value

Usuário pediu último valor:
    /points?path=... -> /streams/{webId}/value

Usuário pediu unidade:
    /points?path=... -> EngineeringUnits

Usuário pediu descrição:
    /points?path=... -> Descriptor

Usuário pediu tipo:
    /points?path=... -> PointType

Usuário pediu digital set:
    /points?path=... -> DigitalSetName

Usuário pediu estados digitais:
    /points?path=... -> DigitalSetName -> /dataservers/{webId}/enumerationsets -> /enumerationsets/{webId}/enumerationvalues

Usuário pediu instrumenttag:
    /points?path=... -> /points/{webId}/attributes?name=instrumenttag

Usuário pediu location1 a location5:
    /points?path=... -> /points/{webId}/attributes?name=location1

Usuário pediu histórico bruto:
    /points?path=... -> /streams/{webId}/recorded

Usuário pediu valores em intervalo fixo:
    /points?path=... -> /streams/{webId}/interpolated

Usuário pediu média/mínimo/máximo:
    /points?path=... -> /streams/{webId}/summary

Usuário pediu gráfico:
    /points?path=... -> /streams/{webId}/plot

Usuário pediu várias tags:
    batch ou streamsets/value
```

---

# CHUNK 17 - Exemplo completo em Python para valor atual

## Intenção

Use este chunk quando for necessário implementar uma tool que consulta o valor atual de uma tag.

## Código

```python
import requests


PIWEBAPI_URL = "http://10.247.224.39/piwebapi"
PI_SERVER = "PIMS"
TIMEOUT_SECONDS = 30


def get_point_by_tag(tag_name: str) -> dict:
    tag_name = tag_name.strip()

    if not tag_name:
        raise ValueError("Nome da tag não informado.")

    response = requests.get(
        f"{PIWEBAPI_URL}/points",
        params={"path": f"\\\\{PI_SERVER}\\{tag_name}"},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def get_current_value(tag_name: str) -> dict:
    point = get_point_by_tag(tag_name)
    web_id = point["WebId"]

    value_url = point.get("Links", {}).get(
        "Value",
        f"{PIWEBAPI_URL}/streams/{web_id}/value",
    )

    response = requests.get(value_url, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    value = response.json()

    return {
        "tag": point.get("Name", tag_name),
        "descriptor": point.get("Descriptor"),
        "point_type": point.get("PointType"),
        "engineering_units": point.get("EngineeringUnits"),
        "digital_set_name": point.get("DigitalSetName"),
        "timestamp": value.get("Timestamp"),
        "value": value.get("Value"),
        "units_abbreviation": value.get("UnitsAbbreviation"),
        "good": value.get("Good"),
        "questionable": value.get("Questionable"),
        "substituted": value.get("Substituted"),
    }


if __name__ == "__main__":
    result = get_current_value("LFI_RB3_VAZ_GN_TOTAL")
    print(result)
```

---

# CHUNK 18 - Exemplo completo em Python para metadados e instrumenttag

## Intenção

Use este chunk quando for necessário implementar uma tool que consulta metadados e atributos clássicos de uma tag.

## Código

```python
import requests


PIWEBAPI_URL = "http://10.247.224.39/piwebapi"
PI_SERVER = "PIMS"
TIMEOUT_SECONDS = 30


def get_point_by_tag(tag_name: str) -> dict:
    tag_name = tag_name.strip()

    if not tag_name:
        raise ValueError("Nome da tag não informado.")

    response = requests.get(
        f"{PIWEBAPI_URL}/points",
        params={"path": f"\\\\{PI_SERVER}\\{tag_name}"},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def get_point_attribute(web_id: str, attribute_name: str):
    response = requests.get(
        f"{PIWEBAPI_URL}/points/{web_id}/attributes",
        params={"name": attribute_name},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    data = response.json()
    items = data.get("Items", [])

    if not items:
        return None

    return items[0].get("Value")


def get_tag_metadata(tag_name: str) -> dict:
    point = get_point_by_tag(tag_name)
    web_id = point["WebId"]

    instrumenttag = get_point_attribute(web_id, "instrumenttag")
    location1 = get_point_attribute(web_id, "location1")
    location2 = get_point_attribute(web_id, "location2")
    location3 = get_point_attribute(web_id, "location3")
    location4 = get_point_attribute(web_id, "location4")
    location5 = get_point_attribute(web_id, "location5")

    return {
        "tag": point.get("Name", tag_name),
        "path": point.get("Path"),
        "descriptor": point.get("Descriptor"),
        "point_class": point.get("PointClass"),
        "point_type": point.get("PointType"),
        "digital_set_name": point.get("DigitalSetName"),
        "engineering_units": point.get("EngineeringUnits"),
        "span": point.get("Span"),
        "zero": point.get("Zero"),
        "step": point.get("Step"),
        "future": point.get("Future"),
        "display_digits": point.get("DisplayDigits"),
        "instrumenttag": instrumenttag,
        "location1": location1,
        "location2": location2,
        "location3": location3,
        "location4": location4,
        "location5": location5,
    }


if __name__ == "__main__":
    result = get_tag_metadata("LFI_RB3_VAZ_GN_TOTAL")
    print(result)
```

---

# CHUNK 19 - O que não fazer

## Intenção

Use este chunk para evitar erros comuns do agente.

## Regras negativas

Não consultar stream usando nome da tag:

```text
Errado:
GET /streams/LFI_RB3_VAZ_GN_TOTAL/value
```

Correto:

```text
GET /points?path=\\PIMS\LFI_RB3_VAZ_GN_TOTAL
GET /streams/{webId}/value
```

Não assumir que uma tag tem digital set se `DigitalSetName` estiver vazio.

Não tratar `Good=false` como zero.

Não inventar unidade se `EngineeringUnits` vier vazio.

Não inventar instrumenttag se o atributo não existir ou vier vazio.

Não usar `recorded` quando o usuário pediu intervalo fixo. Usar `interpolated`.

Não usar `interpolated` quando o usuário pediu eventos reais gravados. Usar `recorded`.

Não somar vazão sem explicar o critério de cálculo.

Não escolher automaticamente uma tag se a busca retornar múltiplas tags parecidas.

---

# CHUNK 20 - Documento mínimo que sempre deveria ser recuperado

## Intenção

Este chunk deve ter alta prioridade no RAG. Ele resume o comportamento central da PI Web API para consultas de tags.

## Resumo operacional

Para consultar qualquer tag no PI Web API:

```text
1. Monte o path da tag:
   \\PIMS\NOME_DA_TAG

2. Busque o PI Point:
   GET http://10.247.224.39/piwebapi/points?path=\\PIMS\NOME_DA_TAG

3. Extraia:
   WebId
   Name
   Descriptor
   PointType
   DigitalSetName
   EngineeringUnits
   Links

4. Para valor atual:
   GET /streams/{WebId}/value

5. Para histórico bruto:
   GET /streams/{WebId}/recorded

6. Para interpolado:
   GET /streams/{WebId}/interpolated

7. Para média/mínimo/máximo/total:
   GET /streams/{WebId}/summary

8. Para instrumenttag/location:
   GET /points/{WebId}/attributes?name=instrumenttag
   GET /points/{WebId}/attributes?name=location1

9. Para digital states:
   usar DigitalSetName -> dataservers/PIMS/enumerationsets -> enumerationvalues
```

## Resposta sempre deve considerar

```text
Valor
Unidade
Timestamp
Qualidade
Descrição da tag
```

## Campos reais importantes no ambiente atual

```text
EngineeringUnits
DigitalSetName
Descriptor
PointType
Links.Value
Links.Attributes
Links.RecordedData
Links.InterpolatedData
Links.SummaryData
Links.PlotData
```
