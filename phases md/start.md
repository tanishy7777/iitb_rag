export DIGITAL_BRAIN_LLM_PROVIDER=ollama
export DIGITAL_BRAIN_OLLAMA_MODEL=llama3
export DIGITAL_BRAIN_OLLAMA_BASE_URL=http://127.0.0.1:11434
export DIGITAL_BRAIN_AUTH_ENABLED=1
export DIGITAL_BRAIN_BOOTSTRAP_ADMIN_USER=admin
export DIGITAL_BRAIN_BOOTSTRAP_ADMIN_PASSWORD=admin123
PYTHONPATH=src python3 -m digital_brain ingest --data-dir data
PYTHONPATH=src python3 -m digital_brain serve --host 127.0.0.1 --port 8080


Enable/disable hybrid flow explicitly:
      - export DIGITAL_BRAIN_FLOW_LLM_ASSIST=1 (enabled)
      - export DIGITAL_BRAIN_FLOW_LLM_ASSIST=0 (force deterministic flow)

UI mode:
cd frontend && npm install && npm run build
export DIGITAL_BRAIN_UI_MODE=react
auto (has fallsback mode)