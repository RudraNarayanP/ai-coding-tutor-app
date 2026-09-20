"""AI course quality patch.

- Verified provider/Python sources for all 28 lessons (OpenAI chat/function-
  calling docs, LlamaIndex, Google ML docs, Dive into Deep Learning, Python
  stdtypes/json docs) — every quoted claim was fetched this session.
- ai-01/02/03: TODO starters that fail their tests, learning objectives, and
  honest descriptions. ai-02 now uses the CURRENT flat tool-definition format
  from the verified OpenAI guide instead of the older nested shape.
- ai-tool-result-msg: uses `call_id` (the field name verified in the OpenAI
  function-calling guide) instead of the legacy `tool_call_id`.

Run:  .venv/Scripts/python.exe backend/patch_ai_quality.py
"""
import json
from pathlib import Path

MOD = Path("curriculum/ai/modules")
PSF = "Python documentation license (PSF)"
GOOGLE = "CC BY 4.0 (Google Machine Learning Crash Course)"
D2LL = "Apache 2.0 (Dive into Deep Learning book)"
LLA = "MIT (LlamaIndex documentation)"
OAI = "OpenAI API documentation (developers.openai.com)"

def py(name, url):
    return {"name": f"Python official documentation (docs.python.org) — {name}", "url": url, "license": PSF}

def oa(name, url):
    return {"name": f"OpenAI documentation — {name}", "url": url, "license": OAI}

SOURCES: dict[str, dict] = {
    "ai-01": oa("Chat Completions API — 'A list of messages comprising the conversation so far'",
                "https://developers.openai.com/api/docs/api-reference/chat"),
    "ai-02": oa("Function calling — tool definition JSON: type 'function', name, description, parameters",
                "https://developers.openai.com/api/docs/guides/function-calling"),
    "ai-03": py("Mapping Types — building logging rows as dicts",
                "https://docs.python.org/3/library/stdtypes.html#mapping-types-dict"),
    "ai-tok-split": py("Text Sequence Type str — str.split() with no arguments splits on whitespace",
                       "https://docs.python.org/3/library/stdtypes.html#string-methods"),
    "ai-tok-lower": py("String Methods — str.lower() and str.strip(chars)",
                       "https://docs.python.org/3/library/stdtypes.html#string-methods"),
    "ai-tok-vocab": py("sorted() — Built-in Functions (alphabetical vocabulary ids)",
                       "https://docs.python.org/3/library/functions.html#sorted"),
    "ai-tok-encode": py("Mapping Types — dict.get(key, default) for unknown-token fallback",
                        "https://docs.python.org/3/library/stdtypes.html#mapping-types-dict"),
    "ai-tok-checkpoint": py("3.1.2 Text — sequences/slicing (tokens[i:i+n])",
                            "https://docs.python.org/3/tutorial/introduction.html#strings"),
    "ai-emb-dot": {"name": "Dive into Deep Learning §2.3 Linear Algebra — dot product is 'a sum over the products of the elements at the same position'",
                   "url": "https://d2l.ai/chapter_preliminaries/linear-algebra.html", "license": D2LL},
    "ai-emb-cosine": {"name": "Google Machine Learning — Measuring similarity from embeddings: 'choose one of these three similarity measures: Cosine'",
                      "url": "https://developers.google.com/machine-learning/clustering/dnn-clustering/supervised-similarity",
                      "license": GOOGLE},
    "ai-emb-topk": {"name": "Dive into Deep Learning §2.3 — dot products ranked across vectors",
                    "url": "https://d2l.ai/chapter_preliminaries/linear-algebra.html", "license": D2LL},
    "ai-emb-meanpool": {"name": "Dive into Deep Learning §2.3 — averaging vectors element-wise",
                        "url": "https://d2l.ai/chapter_preliminaries/linear-algebra.html", "license": D2LL},
    "ai-emb-checkpoint": {"name": "Google Machine Learning — 'The softmax layer maps a vector of scores to a probability distribution'",
                          "url": "https://developers.google.com/machine-learning/recommendation/dnn/softmax",
                          "license": GOOGLE},
    "ai-prompt-system": oa("Chat Completions API — messages array with roles and content",
                           "https://developers.openai.com/api/docs/api-reference/chat"),
    "ai-prompt-template": py("str.format_map — 'Similar to str.format(**mapping), except that mapping is used directly'",
                             "https://docs.python.org/3/library/stdtypes.html#string-methods"),
    "ai-prompt-fewshot": py("Text Sequence Type str — join/formatting to assemble prompt blocks",
                            "https://docs.python.org/3/library/stdtypes.html#string-methods"),
    "ai-prompt-json-schema": py("json — JSON encoder and decoder (structuring model output)",
                                "https://docs.python.org/3/library/json.html"),
    "ai-prompt-checkpoint": py("String Methods — str.find and str.rfind for locating braces",
                               "https://docs.python.org/3/library/stdtypes.html#string-methods"),
    "ai-tool-parse-call": oa("Function calling — 'The model returns a tool call that contains a ... argument'",
                             "https://developers.openai.com/api/docs/guides/function-calling"),
    "ai-tool-dispatch": py("Mapping Types — looking up callables in a dict and **kwargs unpacking",
                           "https://docs.python.org/3/library/stdtypes.html#mapping-types-dict"),
    "ai-tool-validate": py("5.5. Dictionaries — key membership tests for required arguments",
                           "https://docs.python.org/3/tutorial/datastructures.html#dictionaries"),
    "ai-tool-result-msg": oa("Function calling — tool results 'referenced by call_id in the examples to come'",
                             "https://developers.openai.com/api/docs/guides/function-calling"),
    "ai-tool-checkpoint": py("The while/raise machinery + mapping lookup for safe dispatch",
                             "https://docs.python.org/3/library/stdtypes.html#mapping-types-dict"),
    "ai-rag-chunk": {"name": "LlamaIndex — 'Node parsers are a simple abstraction that take a list of documents, and chunk them into Node objects'",
                     "url": "https://developers.llamaindex.ai/python/framework/module_guides/loading/node_parsers/",
                     "license": LLA},
    "ai-rag-index": {"name": "LlamaIndex — 'At a high-level, Indexes are built from Documents'",
                     "url": "https://developers.llamaindex.ai/python/framework/module_guides/indexing/",
                     "license": LLA},
    "ai-rag-retrieve": {"name": "LlamaIndex — indexing for retrieval over chunked documents",
                        "url": "https://developers.llamaindex.ai/python/framework/module_guides/indexing/",
                        "license": LLA},
    "ai-rag-context": {"name": "LlamaIndex — assembling retrieved nodes as context for a query",
                       "url": "https://developers.llamaindex.ai/python/framework/module_guides/indexing/",
                       "license": LLA},
    "ai-rag-checkpoint2": {"name": "LlamaIndex — chunked Nodes carry stable ids and text",
                           "url": "https://developers.llamaindex.ai/python/framework/module_guides/loading/node_parsers/",
                           "license": LLA},
}

LESSON_UPDATES: dict[str, dict] = {
    "ai-01": {
        "description": (
            "Chat completion requests send a 'model' and a 'messages' array — 'a "
            "list of messages comprising the conversation so far' — where each "
            "message is a dict with 'role' and 'content'. Implement "
            "build_chat_payload(model, system_prompt, user_prompt) so it returns "
            "json.dumps of {\"model\": ..., \"messages\": [system, user]}. Tests "
            "parse the JSON and check the model name and that there are 2 messages."
        ),
        "learning_objectives": [
            "Build chat completion request payloads with model and messages",
            "Encode role/content message dicts for system and user turns",
            "Serialize requests with json.dumps",
        ],
        "starter_code": (
            "import json\n\n"
            "def build_chat_payload(model: str, system_prompt: str, user_prompt: str) -> str:\n"
            "    # TODO: assemble {'model': ..., 'messages': [system msg dict, user msg dict]}\n"
            "    #       each message dict has 'role' ('system'/'user') and 'content'\n"
            "    return json.dumps({'model': model, 'messages': []})\n"
        ),
    },
    "ai-02": {
        "description": (
            "Tool definitions let LLMs trigger local functions. The OpenAI "
            "function-calling guide defines a tool as JSON with \"type\": "
            "\"function\", \"name\", \"description\", and a JSON-schema "
            "\"parameters\" object (\"type\": \"object\", \"properties\", "
            "\"required\"). Implement get_sql_query_tool_spec() returning exactly "
            "that structure for a read-only SQL tool: name 'run_sql_query', "
            "description 'Run a read-only SQL query against database', one string "
            "property 'query' described as 'SQL query to execute', required "
            "['query']. Tests check type, name, parameters.properties.query.type "
            "and parameters.required."
        ),
        "learning_objectives": [
            "Declare a function tool with type, name, description, parameters",
            "Describe tool inputs with a JSON schema (properties/required)",
            "Understand that structured tool JSON lets models trigger local code",
        ],
        "starter_code": (
            "def get_sql_query_tool_spec() -> dict:\n"
            "    # TODO: return the tool JSON: type 'function', name 'run_sql_query',\n"
            "    #       description, and a JSON-schema 'parameters' object for `query`\n"
            "    return {\"type\": \"function\", \"name\": \"\", \"description\": \"\", \"parameters\": {}}\n"
        ),
        "solution_code": (
            "def get_sql_query_tool_spec() -> dict:\n"
            "    return {\n"
            "        \"type\": \"function\",\n"
            "        \"name\": \"run_sql_query\",\n"
            "        \"description\": \"Run a read-only SQL query against database\",\n"
            "        \"parameters\": {\n"
            "            \"type\": \"object\",\n"
            "            \"properties\": {\n"
            "                \"query\": {\"type\": \"string\", \"description\": \"SQL query to execute\"}\n"
            "            },\n"
            "            \"required\": [\"query\"]\n"
            "        }\n"
            "    }\n"
        ),
        "tests": [{
            "name": "test_tool_spec",
            "required": True,
            "unittest_code": (
                "def test_tool_spec(self):\n"
                "    spec = get_sql_query_tool_spec()\n"
                "    self.assertEqual(spec['type'], 'function')\n"
                "    self.assertEqual(spec['name'], 'run_sql_query')\n"
                "    self.assertEqual(spec['parameters']['properties']['query']['type'], 'string')\n"
                "    self.assertEqual(spec['parameters']['required'], ['query'])\n"
            ),
        }],
    },
    "ai-03": {
        "description": (
            "RAG evaluation starts by logging conversations as structured rows "
            "(later stored in a table). Implement format_conversation_log(user_id, "
            "prompt, response) returning a dict with keys 'user_id', 'prompt', "
            "'response' and a cheap 'tokens' estimate: "
            "len(prompt.split()) + len(response.split()). Tests check the user id "
            "and that tokens > 0 for a real exchange."
        ),
        "learning_objectives": [
            "Shape conversation logs as dict rows ready for a database insert",
            "Estimate token counts with a whitespace heuristic",
            "Understand that RAG evaluation needs stored prompts and outputs",
        ],
        "starter_code": (
            "def format_conversation_log(user_id: int, prompt: str, response: str) -> dict:\n"
            "    # TODO: return the log dict; 'tokens' = prompt word count + response word count\n"
            "    return {'user_id': user_id, 'prompt': prompt, 'response': response, 'tokens': 0}\n"
        ),
    },
    "ai-tool-result-msg": {
        "description": (
            "After executing a tool, the model must see the result message tied to "
            "the originating call — the OpenAI guide references tool calls by a "
            "`call_id`. Implement tool_result_message(call_id, content) returning "
            "{'role': 'tool', 'call_id': call_id, 'content': content}. Tests check "
            "role, call_id and content."
        ),
        "starter_code": (
            "def tool_result_message(call_id, content):\n"
            "    # TODO: return {'role': 'tool', 'call_id': call_id, 'content': content}\n"
            "    return {}\n"
        ),
        "solution_code": (
            "def tool_result_message(call_id, content):\n"
            "    return {'role': 'tool', 'call_id': call_id, 'content': content}\n"
        ),
        "tests": [{
            "name": "test_tool_result_message",
            "required": True,
            "unittest_code": (
                "def test_tool_result_message(self):\n"
                "    m = tool_result_message('c1', 'ok')\n"
                "    self.assertEqual(m['role'], 'tool')\n"
                "    self.assertEqual(m['call_id'], 'c1')\n"
                "    self.assertEqual(m['content'], 'ok')\n"
            ),
        }],
    },
}


def main() -> int:
    touched = 0
    for path in sorted(MOD.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for lesson in data["lessons"]:
            lid = lesson["id"]
            if lid in SOURCES and not (lesson.get("source") or {}).get("url"):
                lesson["source"] = SOURCES[lid]
                changed = True
            if lid in LESSON_UPDATES:
                lesson.update(LESSON_UPDATES[lid])
                changed = True
        if changed:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
            touched += 1
    print(f"patched {touched} ai modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
