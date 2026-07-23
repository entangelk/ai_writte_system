# Runbook — Local llama.cpp GPU server (opt-in)

For a machine that has **no external llama.cpp endpoint** and wants to run the
full stack self-hosted. The base `docker-compose.yml` deliberately leaves the
llama.cpp server external (per-machine via `LLAMA_BASE_URL`); this override adds
an in-stack `llama` service so nothing outside the compose project is required.

## Contract the server must satisfy

The gateway only needs two endpoints from the llama.cpp-compatible server:

- `GET /health` → `200` when the model is loaded (gateway `/health/ready` probes it).
- `POST /v1/chat/completions` → OpenAI-compatible response
  (`choices[0].message.content`, `finish_reason`, `usage.{prompt,completion}_tokens`)
  with llama.cpp `chat_template_kwargs.enable_thinking` support (needs `--jinja`).

`llama-server` from `ghcr.io/ggml-org/llama.cpp:server-cuda` satisfies both.

## Prerequisites

- NVIDIA GPU + `nvidia-container-toolkit` (the compose `deploy.resources` device
  reservation hands the GPU to the container). Verify with `nvidia-ctk --version`
  and `docker info | grep -i runtime` (should list `nvidia`).
- ~7 GB free disk for the default 12B QAT GGUF (cached in the `llama_models`
  volume; only downloaded once).

CPU-only fallback: drop the `deploy:` block from `docker-compose.llama.yml` and
set `LLAMA_GPU_LAYERS=0` (much slower).

## Run

```bash
# Start just the model server (first run downloads the GGUF; can take minutes):
docker compose -f docker-compose.yml -f docker-compose.llama.yml up -d llama

# Watch load progress until healthy:
docker compose -f docker-compose.yml -f docker-compose.llama.yml logs -f llama
docker compose -f docker-compose.yml -f docker-compose.llama.yml ps   # llama: healthy

# Bring up the whole stack (gateway waits for llama to be healthy):
docker compose -f docker-compose.yml -f docker-compose.llama.yml up -d
```

Direct server check:

```bash
curl -fsS http://localhost:9080/health
curl -fsS http://localhost:8521/health/ready   # gateway -> llama upstream readiness
```

## Configuration (env overrides)

| Env | Default | Purpose |
|---|---|---|
| `LLAMA_HF_REPO` | `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0` | GGUF the server loads via `-hf` |
| `LLAMA_DEFAULT_MODEL` | same as `LLAMA_HF_REPO` | `model` field the gateway sends |
| `LLAMA_GPU_LAYERS` | `99` | layers offloaded to GPU (`0` = CPU only) |
| `LLAMA_CTX_SIZE` | `8192` | context window |
| `LLAMA_PORT` | `9080` | host port for the server |
| `LLAMA_TIMEOUT_SECONDS` | `900` | gateway → llama request timeout |
| `APPLICATION_PORT` / `GATEWAY_PORT` / `MONGO_PORT` | `8000` / `8001` / `27017` | host ports (base compose) |

The 12B QAT model is slow (~5 t/s observed); keep `LLAMA_TIMEOUT_SECONDS` and any
smoke `--timeout-seconds` generous (900–1000 s). If the GPU OOMs on the 12B,
lower `LLAMA_GPU_LAYERS` or `LLAMA_CTX_SIZE`, or set `LLAMA_HF_REPO` to a smaller
gemma GGUF.

## Smoke against the running stack

```bash
# Phase 4 planner live smoke (in-process gateway → real llama):
LLAMA_BASE_URL=http://localhost:9080 \
python3 scripts/phase4_context_search_planner_live_smoke.py --timeout-seconds 1000

# Phase 2A deployed E2E (already-running Application HTTP endpoint):
python3 scripts/phase2a_deployed_e2e_smoke.py \
  --application-base-url http://127.0.0.1:8000 --timeout-seconds 1000
```

## Teardown

```bash
docker compose -f docker-compose.yml -f docker-compose.llama.yml down
# add -v to also delete the cached model (llama_models volume)
```
