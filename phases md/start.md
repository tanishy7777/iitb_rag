export DIGITAL_BRAIN_LLM_PROVIDER=ollama
  export DIGITAL_BRAIN_OLLAMA_MODEL=llama3
  export DIGITAL_BRAIN_OLLAMA_BASE_URL=http://127.0.0.1:11434
  PYTHONPATH=src python3 -m digital_brain ingest --data-dir data
  PYTHONPATH=src python3 -m digital_brain serve --host 127.0.0.1 --port 8080