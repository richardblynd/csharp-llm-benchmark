# Plano: KV Cache Quantization no Benchmark

## Objetivo

Adicionar suporte para registrar e filtrar a quantização do **KV cache** de forma separada da quantização de pesos do modelo. Isso permite comparar o mesmo modelo (mesma quantização de pesos) executado com diferentes quantizações de KV cache, e vice-versa.

## Contexto atual

- O campo `llm.quantization` captura a quantização de **pesos** do modelo (ex: Q4_K_M, Q8_0).
- Para GPT (cloud/OpenAI), esse campo usa `"-"`.
- A página HTML já possui filtro e coluna "Quant." — mas refere-se apenas à quantização de pesos.
- Todos os benchmarks locais rodados até agora usaram **KV cache em Q4** (exceto os GPT que rodam na nuvem).

## Decisões de design

| Decisão | Escolha | Justificativa |
|---|---|---|
| Nome do campo no YAML | `kv_cache_quantization` | snake_case, autoexplicativo |
| Tipo do valor | string livre ou null | ex: `"Q4"`, `"Q8"`, `"none"` |
| Valor para GPT cloud | `null` (omitido) | Não se aplica a modelos na nuvem; sem valor explícito como `"-"` |
| Inclui no nome da pasta do run? | Não | Manter compatibilidade com pastas existentes e não poluir o path |

## Mudanças necessárias

### 1. Config layer — `benchmark/config.py` + `config.example.yaml`

- **LlmConfig**: adicionar campo `kv_cache_quantization: str | None = None`.
- **load_config()**: ler `llm.kv_cache_quantization` do YAML via `_optional_string()`.
- **apply_cli_overrides()**: propagar o valor sem override por CLI (é configuração de ambiente, não de execução ad-hoc).
- **config.example.yaml**: adicionar exemplo comentado:

  ```yaml
  # Quantização do KV cache. Omitir ou usar null se não se aplica (ex: GPT cloud).
  # kv_cache_quantization: "Q4"
  ```

### 2. Report layer — `benchmark/report.py`

- **write_summary()**: incluir `kv_cache_quantization` no payload de topo e dentro do bloco `llm`:

  ```python
  "kv_cache_quantization": config.llm.kv_cache_quantization,
  # dentro de llm:
  "kv_cache_quantization": config.llm.kv_cache_quantization,
  ```

- **_render_markdown()**: adicionar linha no summary.md:

  ```python
  f"- KV cache quantization: `{payload.get('kv_cache_quantization') or 'n/a'}`",
  ```

### 3. Aggregate / HTML layer — `benchmark/aggregate_benchmark_results.py`

#### Dataclass BenchmarkResult

- Adicionar campo `kv_cache_quantization: str | None`.

#### parse_summary()

- Ler do summary.json:

  ```python
  kv_cache_quantization = (
      str(payload.get("kv_cache_quantization")) or
      llm_payload.get("kv_cache_quantization")
  ) or None
  if not kv_cache_quantization:
      kv_cache_quantization = None
  ```

#### Tabela Markdown

- Adicionar coluna "KV cache" após a coluna "Quantization".

#### Página HTML — estrutura

- **Filtro**: novo `<select id="kvCacheQuant">` na seção `.filters`, coletando valores únicos de `result.kv_cache_quantization` (incluindo um entry para runs sem KV cache).
- **Coluna**: nova coluna "KV Q" no thead e tbody, logo após a coluna "Quant.".
- **Row data attr**: `data-kv-cache-quant="..."` em cada `<tr>`.
- **JavaScript filtro**: na função `rowMatches()`, verificar `row.dataset.kvCacheQuant` quando o select estiver ativo.
- **Estado localStorage**: incluir `kvCacheQuant` no objeto salvo/restaurado.

#### Gráficos

- O score chart e tradeoff chart já exibem a quantização de pesos. Para o tradeoff, a legenda pode agrupar por combinação model+quant+kv ou manter status quo (apenas pesos) — avaliar se vale diferenciar. Por enquanto, sem mudança nos gráficos.

### 4. Script de migração — resultados existentes

Um script Python curto que backfilla os `summary.json` já existentes:

```python
import json
from pathlib import Path

results_dir = Path("results")
for run_dir in sorted(d for d in results_dir.iterdir() if d.is_dir()):
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        continue
    data = json.loads(summary_path.read_text())

    # Idempotente: só aplica se o campo ainda não existe
    if "kv_cache_quantization" in data:
        continue

    base_url = str(data.get("llm", {}).get("base_url", ""))
    is_gpt_cloud = "api.openai.com" in base_url

    new_value = None if is_gpt_cloud else "Q4"
    data["kv_cache_quantization"] = new_value
    data.setdefault("llm", {})["kv_cache_quantization"] = new_value

    summary_path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
```

**Regra:** Se `llm.base_url` contém `api.openai.com` → GPT cloud → `null`. Caso contrário → run local → `"Q4"`.

### 5. Documentação — `PROJECT_CONTEXT.md`

Atualizar os trechos que descrevem:

- **config.py**: mencionar o novo campo `kv_cache_quantization` na seção de `llm`.
- **report.py / summary.json**: mencionar que o payload inclui `kv_cache_quantization` no topo e dentro de `llm`.
- **aggregate_benchmark_results.py**: mencionar a coluna adicional KV Q e o filtro HTML.

## Ordem de implementação

1. Config layer (`config.py` + `config.example.yaml`)
2. Report layer (`report.py`)
3. Aggregate / HTML layer (`aggregate_benchmark_results.py`)
4. Script de migração — backfill resultados existentes
5. Regerar HTML: rodar o aggregate para atualizar o dashboard
6. Documentação (`PROJECT_CONTEXT.md`)

## Validação

- Rodar `python3 -m benchmark.cli validate` após mudanças em config/tasks.
- Executar um benchmark curto (ex: `--difficulty easy --task-id easy-001`) com `kv_cache_quantization: "Q8"` e verificar que aparece no summary.json, na tabela HTML e no filtro.
- Rerodar o aggregate script e confirmar que a coluna KV Q exibe corretamente para todos os runs (incluindo os backfillados).
