# Local Coding Tutor

- Keep all AI calls local through the Ollama provider at `http://localhost:11434`.
- Keep Python execution and test results independent from the LLM.
- Preserve the `AIProvider` abstraction when changing model integrations.
- Never add cloud AI APIs or send student code off-device.
