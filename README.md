# Patchwork Local Coding Tutor

Patchwork is an offline-first, deterministic local coding tutor with an interactive beginner learning progression and provider-agnostic AI hints.

## AI Provider Setup

Patchwork supports multiple interchangeable AI providers:

- **Ollama (Local)** (default)
- **OpenAI**
- **Anthropic Claude**
- **OpenRouter**
- **Google Gemini**

AI API keys remain **strictly server-side** and are never exposed to the frontend browser.

### Environment Configuration

Copy `.env.example` to `.env` or export environment variables before launching the backend:

```bash
# Select Provider
export AI_PROVIDER=ollama  # Options: ollama, openai, anthropic, openrouter, gemini
export AI_FALLBACK_PROVIDER=  # Optional fallback provider

# Ollama
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=llama3.1:8b

# OpenAI
export OPENAI_API_KEY=your_openai_api_key
export OPENAI_MODEL=gpt-4o-mini

# Anthropic
export ANTHROPIC_API_KEY=your_anthropic_api_key
export ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

# OpenRouter
export OPENROUTER_API_KEY=your_openrouter_api_key
export OPENROUTER_MODEL=meta-llama/llama-3.1-8b-instruct:free

# Google Gemini
export GEMINI_API_KEY=your_gemini_api_key
export GEMINI_MODEL=gemini-1.5-flash
```

## Running Patchwork Locally

1. **Start Backend Service:**
   ```bash
   .venv/bin/uvicorn backend.main:app --port 8000 --reload
   ```

2. **Start Frontend Application:**
   ```bash
   npm run dev
   ```

3. **Run Tests:**
   ```bash
   # Backend tests
   .venv/bin/pytest backend/

   # Frontend tests
   npx vitest run

   # Frontend production build
   npm run build
   ```
