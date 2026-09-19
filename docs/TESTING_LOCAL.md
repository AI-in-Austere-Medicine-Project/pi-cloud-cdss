# Testing the local model (manual checks)

These checks run a **second** server on port 8001. Do not restart
`edgecdss.service` (port 8000) or edit `server/.env` for them.

The second server is started from `server/`, so it loads the same `server/.env`
as production, keys included. `load_dotenv()` never overrides a variable that is
already set, so every command below sets two things explicitly:

- `CDSS_LOG_DIR` points at a scratch directory, so test answers never enter the
  production session log.
- `CHROMADB_PATH` points at a **copy** of the corpus, so the two servers never
  share one ChromaDB.

## One-time setup

```bash
ollama list                      # qwen2.5:3b must be listed
curl -s localhost:11434/api/version
mkdir -p /tmp/cdss-local/logs
cp -r ~/pi-cloud-cdss/server/cache/chromadb /tmp/cdss-local/chromadb   # or the eval copy
```

## 1. Local provider: the badge shows

```bash
cd ~/pi-cloud-cdss/server
CDSS_LLM_PROVIDER=local \
CDSS_LOG_DIR=/tmp/cdss-local/logs CHROMADB_PATH=/tmp/cdss-local/chromadb \
  ../.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8001
```

1. Open `http://127.0.0.1:8001/` and ask a question that reaches the generator,
   for example *how do I manage a tension pneumothorax in the field*.
2. **Expect:** a blue **local model · offline** badge in the row under the
   answer, beside the validator badge and the latency. The footer reads
   *Answered by local/qwen2.5:3b*. Hovering the badge shows *Answered by the
   on-device model*.
3. Ask for a deterministic card, for example *need to make push dose epi*.
   **Expect:** no badge. No model wrote the card, and the footer says so.
4. `tail -1 /tmp/cdss-local/logs/cdss_session_*.jsonl` has `"provider": "local"`,
   `"validator_provider": "local"` and `"log_schema": 12`.

## 2. Hybrid fallback: the badge shows, stamped as a fallback

Point the cloud provider at a closed port. That is a connection error, the case
the fallback exists for:

```bash
CDSS_OPENAI_BASE_URL=http://127.0.0.1:9/v1 \
CDSS_LOG_DIR=/tmp/cdss-local/logs CHROMADB_PATH=/tmp/cdss-local/chromadb \
  ../.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8001
```

- Ask the same generated question.
- **Expect:** the same badge, with the hover text *Cloud unreachable; answered by
  the on-device model*. The server console prints
  `openai/gpt-4o-mini unreachable (APIConnectionError) — retrying on
  local/qwen2.5:3b`.
- The log line has `"provider": "local-fallback"`.
- For the timeout path, use `CDSS_OPENAI_BASE_URL=http://10.255.255.1/v1`
  (unroutable) with `CDSS_LLM_CLOUD_TIMEOUT=2`. Expect the same result, about 2 s
  later.

## 3. An auth error is not hidden

```bash
OPENAI_API_KEY=sk-not-a-real-key-000000 \
CDSS_LOG_DIR=/tmp/cdss-local/logs CHROMADB_PATH=/tmp/cdss-local/chromadb \
  ../.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8001
```

- Ask a generated question.
- **Expect:** a **SYSTEM ERROR** badge and no local answer. OpenAI refused the
  key (401). The network worked, so this is not the fallback's case, and the
  operator has to see it.

## 4. Cloud: nothing changed

Start the second server with none of the `CDSS_LLM_*` variables set. Generated
answers show no badge, and the log line has `"provider": "openai"`.
