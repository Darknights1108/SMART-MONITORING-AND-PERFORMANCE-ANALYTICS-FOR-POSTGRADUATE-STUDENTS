#!/bin/bash
# Wait for Ollama to be ready, then pull the required models

echo "Waiting for Ollama to start..."
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 2
done

echo "Pulling Qwen3 8B model..."
ollama pull qwen3:8b

echo "Pulling BGE-M3 embedding model..."
ollama pull bge-m3

echo "All models ready!"
