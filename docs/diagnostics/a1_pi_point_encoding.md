# Diagnóstico A1: Comparação Batch vs GET direto

## Data: 03/08/2026

## Tag: `LFS_RB2_AC_MA_VIB_VEL`

## Resultado

**Todos os 4 cenários retornam a tag com sucesso.** A hipótese H1 (encoding de `\`) é **REFUTADA**.

## Cenários testados

### Cenário 1: Batch com sub-request (POST /batch)

```json
{
    "point_0": {
        "Status": 200,
        "Content": {
            "WebId": "F1DPxhF1MCtATE6DjgaMSVY2gg6oQBAAUElNU1xMRlNfUkIyX0FDX01BX1ZJQl9WRUw",
            "Name": "LFS_RB2_AC_MA_VIB_VEL",
            "Descriptor": "VELOCIDADE DO MANCAL A DO AR DE COMBUSTÃO",
            "PointType": "Float32",
            "EngineeringUnits": "mm/s"
        }
    }
}
```

### Cenário 2: GET direto (URL-encoded: `%5C%5CPIMS%5C`)

```json
{
    "WebId": "F1DPxhF1MCtATE6DjgaMSVY2gg6oQBAAUElNU1xMRlNfUkIyX0FDX01BX1ZJQl9WRUw",
    "Name": "LFS_RB2_AC_MA_VIB_VEL",
    "Descriptor": "VELOCIDADE DO MANCAL A DO AR DE COMBUSTÃO",
    "PointType": "Float32",
    "EngineeringUnits": "mm/s"
}
```

### Cenário 3: GET direto (path literal: `\\PIMS\`)

```json
{
    "WebId": "F1DPxhF1MCtATE6DjgaMSVY2gg6oQBAAUElNU1xMRlNfUkIyX0FDX01BX1ZJQl9WRUw",
    "Name": "LFS_RB2_AC_MA_VIB_VEL",
    "Descriptor": "VELOCIDADE DO MANCAL A DO AR DE COMBUSTÃO",
    "PointType": "Float32",
    "EngineeringUnits": "mm/s"
}
```

### Cenário 4: GET com --data-urlencode

```json
{
    "WebId": "F1DPxhF1MCtATE6DjgaMSVY2gg6oQBAAUElNU1xMRlNfUkIyX0FDX01BX1ZJQl9WRUw",
    "Name": "LFS_RB2_AC_MA_VIB_VEL",
    "Descriptor": "VELOCIDADE DO MANCAL A DO AR DE COMBUSTÃO",
    "PointType": "Float32",
    "EngineeringUnits": "mm/s"
}
```

## Análise

### Formato da resposta GET

A resposta GET do PI Web API para `/points?path=...` retorna o point **diretamente**, sem wrapper `Items`:

```json
{
    "WebId": "...",
    "Name": "LFS_RB2_AC_MA_VIB_VEL",
    "Descriptor": "...",
    "PointType": "Float32",
    "EngineeringUnits": "mm/s"
}
```

### Formato da resposta Batch

A resposta Batch retorna o point dentro de `Content`:

```json
{
    "point_0": {
        "Status": 200,
        "Content": {
            "WebId": "...",
            "Name": "LFS_RB2_AC_MA_VIB_VEL",
            ...
        }
    }
}
```

### Causa raiz do bug

O `PiDataCollector.fetch_one` verifica `metadata_raw.get("Items")`:

```python
metadata_raw = await get_point_by_tag(tag)
if not metadata_raw or not metadata_raw.get("Items"):
    return AnalysisError(
        tag=tag,
        code="TAG_NOT_FOUND",
        message=f"Tag não encontrada: {tag}",
        retryable=False,
    )
```

Mas a resposta GET do PI Web API **não** tem `Items`! O point é retornado diretamente. Então `metadata_raw.get("Items")` retorna `None`, e a condição é `True`, gerando `TAG_NOT_FOUND`.

### Conclusão

- **H1 (encoding)**: REFUTADA — ambos os transportes funcionam.
- **Causa real**: `PiDataCollector.fetch_one` espera `Items` que não existe na resposta GET.
- **O resolver canônico com Batch como transporte primário** resolve o problema porque:
  1. O Batch retorna `Content` (não `Items`), que é processado corretamente por `format_pi_batch_response`.
  2. O GET direto retorna o point sem wrapper, que precisa de tratamento diferente.
  3. O resolver unifica o transporte e o parsing, eliminando a assimetria.
