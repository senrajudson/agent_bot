# PI Web API Agent Guide

Purpose-built reference for agents querying data from the PI System via PI Web API. This guide focuses on **reading data and information** — no maintenance, no administration, no writes.

**Base URL**: `http://10.247.224.39/piwebapi`

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Finding Points and Elements](#finding-points-and-elements)
3. [Reading Time Series Data](#reading-time-series-data)
4. [Bulk Data Retrieval](#bulk-data-retrieval)
5. [Querying Event Frames](#querying-event-frames)
6. [AF Hierarchy Navigation](#af-hierarchy-navigation)
7. [Search Operations](#search-operations)
8. [System Information](#system-information)
9. [Error Handling](#error-handling)
10. [Common Patterns](#common-patterns)

---

## Quick Start

### Get current value of a PI Point by path
```bash
curl -s "http://10.247.224.39/piwebapi/points?path=\\PIMS\sinusoid" | jq '.WebId'
```

### Get the value using the WebId from Links
```bash
# Use the Value link from the response:
curl -s "http://10.247.224.39/piwebapi/streams/F1DPxhF1MCtATE6DjgaMSVY2ggh0AAAAAU1NU1xMRklfUkIzX1pBW19IV19UT1RBTA/value"
```

### Get historical data
```bash
curl -s "http://10.247.224.39/piwebapi/streams/{webId}/recorded?startTime=-1d&endTime=*"
```

---

## Finding Points and Elements

### PI Point by Path
```
GET http://10.247.224.39/piwebapi/points?path=\\PIMS\sinusoid
```
Returns: WebId, Name, PointClass, PointType, EngineeringUnits, Span, Zero, Step, and links to data.

Example response from `http://10.247.224.39/piwebapi/points?path=\\PIMS\LFI_RB3_VAZ_GN_TOTAL`:
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

### AF Element by Path
```
GET http://10.247.224.39/piwebapi/elements?path=\\PIMS\MyDB\MyElement
```

### AF Attribute by Path
```
GET http://10.247.224.39/piwebapi/attributes?path=\\PIMS\MyDB\MyElement|Temperature
```

### Get Element's Attributes
```
GET http://10.247.224.39/piwebapi/elements/{webId}/attributes
```

### Get Attribute Value (Non-Time-Series)
```
GET http://10.247.224.39/piwebapi/attributes/{webId}/value
```

---

## Reading Time Series Data

All time series data goes through **Stream** endpoints. The WebId comes from a PI Point or an Attribute with a PI Point data reference.

### Current Value
```
GET http://10.247.224.39/piwebapi/streams/{webId}/value
```
Returns the latest value with timestamp, quality, and units.

### Recorded Values (Historical Raw Data)
```
GET http://10.247.224.39/piwebapi/streams/{webId}/recorded
  ?startTime=-1d
  &endTime=*
  &maxCount=1000
```
| Parameter | Description |
|-----------|-------------|
| `startTime` | Start of time range (PI time string) |
| `endTime` | End of time range (`*` = now) |
| `maxCount` | Max values returned |
| `boundaryType` | `Inside` (default) or `Outside` |
| `retrievalMode` | `Auto`, `AtOrBefore`, `Before`, `AtOrAfter`, `After`, `Exact` |

### Interpolated Values (Gap-Filled)
```
GET http://10.247.224.39/piwebapi/streams/{webId}/interpolated
  ?startTime=-1d
  &endTime=*
  &interval=1h
```
| Parameter | Description |
|-----------|-------------|
| `interval` | Spacing between values (`15m`, `1h`, `1d`) |
| `syncTime` | Anchor time to prevent interval drift |

### Plot Values (For Charts)
```
GET http://10.247.224.39/piwebapi/streams/{webId}/plot
  ?startTime=-8h
  &endTime=*
  &intervals=500
```
Returns an optimized subset of values for display.

### Summary Values (Aggregations)
```
GET http://10.247.224.39/piwebapi/streams/{webId}/summary
  ?startTime=-1d
  &endTime=*
  &summaryType=Average
  &summaryType=Maximum
```
| `summaryType` | Description |
|---------------|-------------|
| `Total` | Totalization |
| `Average` | Average value |
| `Minimum` | Minimum value |
| `Maximum` | Maximum value |
| `Range` | Max - Min |
| `StdDev` | Standard deviation |
| `Count` | Number of events |
| `PercentGood` | % of time with good data |
| `All` | All summary types |

Additional parameters:
- `calculationBasis`: `TimeWeighted` (default) or `EventWeighted`
- `duration`: For time-bucketed summaries (e.g., `1h` for hourly averages)
- `timeType`: `Auto`, `EarliestTime`, or `MostRecentTime`

---

## Bulk Data Retrieval

Stream Sets retrieve data for **multiple attributes** in one call.

### Hierarchical (Same Parent Element)
```
GET http://10.247.224.39/piwebapi/streamsets/{webId}/value
GET http://10.247.224.39/piwebapi/streamsets/{webId}/recorded
GET http://10.247.224.39/piwebapi/streamsets/{webId}/interpolated
GET http://10.247.224.39/piwebapi/streamsets/{webId}/summaries
```
| Parameter | Description |
|-----------|-------------|
| `fieldNameFilter` | Comma-separated attribute names (e.g., `Temperature,Pressure`) |
| `categoryNameFilter` | Filter by attribute category |

### Ad-Hoc (Arbitrary Points)
```
GET http://10.247.224.39/piwebapi/streamsets/value?webId={id1}&webId={id2}
GET http://10.247.224.39/piwebapi/streamsets/recorded?webId={id1}&webId={id2}
GET http://10.247.224.39/piwebapi/streamsets/interpolated?webId={id1}&webId={id2}
```
**When**: Need data from unrelated points across different elements.

---

## Querying Event Frames

### Event Frames for an Element
```
GET http://10.247.224.39/piwebapi/elements/{webId}/eventframes
```

### Event Frames for a Database
```
GET http://10.247.224.39/piwebapi/assetdatabases/{webId}/eventframes
```

### Search Event Frames
```
GET http://10.247.224.39/piwebapi/assetdatabases/{webId}/eventframes
  ?searchQuery=Name:=Shutdown* Template:ProcessTemplate
```

| Search Filter | Example |
|---------------|---------|
| `Name:=Pattern*` | Name with wildcards |
| `Template:TemplateName` | Filter by template |
| `Category:CategoryName` | Filter by category |
| `Element:ParentName` | Filter by parent element |
| `Start:>-1w` | Started after 1 week ago |
| `End:<*` | Ended before now |
| `InProgress:true` | Currently active |
| `Severity:Critical` | Filter by severity |

### Event Frame Search Modes
| Mode | Description |
|------|-------------|
| `StartInclusive` | Start time within range |
| `EndInclusive` | End time within range |
| `Inclusive` | Both start and end within range |
| `Overlapped` | Overlaps with range |
| `InProgress` | Started in range, no end time |

### Get Event Frame Attributes
```
GET http://10.247.224.39/piwebapi/eventframes/{webId}/attributes
```

### Get Event Frame Referenced Elements
```
GET http://10.247.224.39/piwebapi/eventframes/{webId}/referencedelements
```

---

## AF Hierarchy Navigation

### List Asset Servers
```
GET http://10.247.224.39/piwebapi/assetservers
```

### Get Databases for a Server
```
GET http://10.247.224.39/piwebapi/assetservers/{webId}/databases
```

### Get Elements in a Database
```
GET http://10.247.224.39/piwebapi/assetdatabases/{webId}/elements
```

### Get Child Elements
```
GET http://10.247.224.39/piwebapi/elements/{webId}/elements
```

### Get Element Templates
```
GET http://10.247.224.39/piwebapi/assetdatabases/{webId}/elementtemplates
```

### Navigation Pattern (HATEOAS)
Every response includes a `Links` object. Follow links instead of constructing URLs:
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

## Search Operations

### PI Point Search
```
GET http://10.247.224.39/piwebapi/points/{dataServerWebId}/search
  ?query=tag:sin* AND PointType:Float64
```

| Query Syntax | Description |
|--------------|-------------|
| `tag:=sin*` | PI Point name with wildcard |
| `PointType:Float64` | Data type filter |
| `PointSource:L` | Point source filter |
| `Value:>100` | Current value filter |
| `AND`, `OR` | Logical operators |

### AF Element Search
```
GET http://10.247.224.39/piwebapi/assetdatabases/{webId}/elements
  ?searchQuery=Name:=Pump* Template:Centrifugal
```

### AF Attribute Search
```
GET http://10.247.224.39/piwebapi/assetdatabases/{webId}/attributes
  ?searchQuery=Name:=Temperature*
```

---

## System Information

### API Root (Discover All Links)
```
GET http://10.247.224.39/piwebapi/
```

### Server Status
```
GET http://10.247.224.39/piwebapi/system/status
```

### Current User Info
```
GET http://10.247.224.39/piwebapi/system/userinfo
```

### List Data Servers
```
GET http://10.247.224.39/piwebapi/dataservers
```

### Get Data Server Points
```
GET http://10.247.224.39/piwebapi/dataservers/{webId}/points
```

---

## Error Handling

### Status Codes
| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Process response |
| 400 | Bad Request | Check parameters |
| 401 | Unauthorized | Check credentials |
| 403 | Forbidden | Check permissions |
| 404 | Not Found | Verify path/WebId |
| 500 | Server Error | Retry later |

### Stream Value Errors
Individual values may contain errors while the overall request succeeds:
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

## Common Patterns

### Get Current Value of a PI Point
```bash
# Step 1: Get WebId from path
WEBID=$(curl -s "http://10.247.224.39/piwebapi/points?path=\\PIMS\sinusoid" | jq -r '.WebId')

# Step 2: Get current value
curl -s "http://10.247.224.39/piwebapi/streams/$WEBID/value"
```

### Get Historical Data for a PI Point
```bash
WEBID=$(curl -s "http://10.247.224.39/piwebapi/points?path=\\PIMS\sinusoid" | jq -r '.WebId')
curl -s "http://10.247.224.39/piwebapi/streams/$WEBID/recorded?startTime=-7d&endTime=*&maxCount=500"
```

### Get Hourly Averages for Last 24h
```bash
WEBID=$(curl -s "http://10.247.224.39/piwebapi/points?path=\\PIMS\sinusoid" | jq -r '.WebId')
curl -s "http://10.247.224.39/piwebapi/streams/$WEBID/summary?startTime=-1d&endTime=*&summaryType=Average&duration=1h"
```

### Get All Attributes of an Element
```bash
ELEMENT_WEBID=$(curl -s "http://10.247.224.39/piwebapi/elements?path=\\PIMS\MyDB\Pump1" | jq -r '.WebId')
curl -s "http://10.247.224.39/piwebapi/elements/$ELEMENT_WEBID/attributes"
```

### Get Current Values for Multiple Points
```bash
# Using ad-hoc stream set
WEBID1=$(curl -s "http://10.247.224.39/piwebapi/points?path=\\PIMS\sinusoid" | jq -r '.WebId')
WEBID2=$(curl -s "http://10.247.224.39/piwebapi/points?path=\\PIMS\cdt158" | jq -r '.WebId')
curl -s "http://10.247.224.39/piwebapi/streamsets/value?webId=$WEBID1&webId=$WEBID2"
```

### Find Active Event Frames
```bash
curl -s "http://10.247.224.39/piwebapi/assetdatabases/{dbWebId}/eventframes?searchQuery=InProgress:true"
```

### Export Database Structure as XML
```
GET http://10.247.224.39/piwebapi/assetdatabases/{webId}/export?mode=Default
```

### Performance Equation Calculation
```
GET http://10.247.224.39/piwebapi/calculations
  ?expression='sinusoid'*2
  &startTime=-1h
  &endTime=*
  &interval=1m
```

---

## Quick Reference: Endpoint Selection

| Need | Endpoint |
|------|----------|
| Current value | `GET /streams/{webId}/value` |
| Historical raw data | `GET /streams/{webId}/recorded` |
| Gap-filled data | `GET /streams/{webId}/interpolated` |
| Aggregated stats | `GET /streams/{webId}/summary` |
| Chart data | `GET /streams/{webId}/plot` |
| Multiple streams | `/streamsets/...` endpoints |
| Find PI Point | `GET /points?path=\\...` |
| Find Element | `GET /elements?path=\\...` |
| Find Attribute | `GET /attributes?path=\\...` |
| List elements in DB | `GET /assetdatabases/{webId}/elements` |
| Element attributes | `GET /elements/{webId}/attributes` |
| Event frames | `GET /elements/{webId}/eventframes` |
| Search points | `GET /points/{webId}/search?query=...` |
| Server info | `GET /system/status` |

---

## Time Strings

| Format | Meaning |
|--------|---------|
| `*` | Now |
| `*-1h` | 1 hour ago |
| `*-1d` | 1 day ago |
| `*-7d` | 7 days ago |
| `T` | Today at midnight |
| `Y` | Yesterday at midnight |
| `Monday` | Most recent Monday at midnight |
| `2024-01-01T00:00:00Z` | Absolute UTC time |
| `2024-01-01T00:00:00-05:00` | With timezone offset |

**Standard Intervals**: `ms`, `s`, `m`, `h`, `d`, `mo`, `w`, `wd`, `yd`

---

## URL Encoding

Special characters in PI paths must be percent-encoded:

| Character | Encoding |
|-----------|----------|
| `\` | `%5C` |
| `|` | `%7C` |
| `#` | `%23` |
| Space | `%20` |
| `:` | `%3A` |

---

## WebID Types

WebIDs identify PI/AF objects. The first character indicates the type:

| Type | First Char | Description |
|------|-----------|-------------|
| Full | `F` | Complete identifier (recommended) |
| ID Only | `I` | GUID-based |
| Path Only | `P` | Path-based |
| Local ID | `L` | Local GUID |
| Default | `D` | Default identifier |

---

## Server

`http://10.247.224.39/piwebapi`
