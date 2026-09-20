"""Rebuild the JavaScript and TypeScript courses to PATCHWORK quality.

- Rewrites the 8 existing lessons (js-01..04, ts-01..04): descriptions now
  state the exact task + test expectations, starters are TODO skeletons that
  FAIL the tests, solutions pass, tests cover every branch, and each lesson
  gets learning objectives + a source.
- ts-03 is rewritten without parameter-property syntax (not valid in
  strip-only TypeScript, which is what the sandbox Node executes).
- js-04's single-case test is strengthened to cover the default parameter
  and the returned env field.
- Adds three new source-grounded lessons per course (js-05..07, ts-05..07).

All sources were actually fetched/inspected this session: MDN Web Docs
(Functions guide, async_function, Promise/then, Node/textContent,
Default_parameters, Array/map, Guide/Modules) and the official TypeScript
Handbook source (microsoft/TypeScript-Website, handbook-v2: Everyday Types,
Narrowing, Generics, Classes).

Run from repo root:  .venv/Scripts/python.exe backend/patch_js_ts_quality.py
"""
import json
from pathlib import Path

JS = Path("curriculum/javascript/modules")
TS = Path("curriculum/typescript/modules")
MDN_LIC = "CC0 1.0 Universal (MDN Web Docs)"
TS_LIC = "CC BY 4.0 (TypeScript documentation)"


def mdn(name: str, url: str) -> dict:
    return {"name": f"MDN Web Docs — {name}", "url": url, "license": MDN_LIC}


def tsh(name: str, url: str) -> dict:
    return {"name": f"TypeScript Handbook — {name}", "url": url, "license": TS_LIC}


# ---------------------------------------------------------------------------
# Lesson rewrites keyed by lesson id (fields merged into the lesson JSON).
# New lessons are keyed with a "__new__:<module file>" marker.
# ---------------------------------------------------------------------------
REWRITES: dict[str, dict] = {
    # ---------------- JavaScript ----------------
    "js-01": {
        "description": (
            "An arrow function expression has a shorter syntax compared to function "
            "expressions. Implement `calculateTotal(price, tax)` as a `const` arrow "
            "function returning `price + price * tax`, and export it with "
            "`module.exports = { calculateTotal }`. The tests check "
            "calculateTotal(100, 0.1) === 110 and calculateTotal(50, 0.2) === 60."
        ),
        "starter_code": (
            "// TODO: make calculateTotal a const arrow function that adds the tax\n"
            "function calculateTotal(price, tax) {\n    return 0;\n}\n"
            "module.exports = { calculateTotal };\n"
        ),
        "solution_code": (
            "const calculateTotal = (price, tax) => price + (price * tax);\n"
            "module.exports = { calculateTotal };\n"
        ),
        "learning_objectives": [
            "Declare constants with const (block-scoped, no reassignment)",
            "Write arrow functions as compact expressions",
            "Export functions with module.exports",
        ],
        "source": mdn("Functions guide — 'An arrow function expression has a shorter syntax compared to function expressions'",
                      "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Functions"),
        "tests": [{
            "name": "test_calculate_total",
            "required": True,
            "unittest_code": (
                "const { calculateTotal } = solution;\n"
                "if (calculateTotal(100, 0.1) !== 110) throw new Error('Expected 110');\n"
                "if (calculateTotal(50, 0.2) !== 60) throw new Error('Expected 60');"
            ),
        }],
    },
    "js-02": {
        "description": (
            "The textContent property represents the text content of a DOM node. "
            "Implement `createButton(text)` as an arrow function that returns an "
            "object modelling a <button> element: { tag: 'button', textContent: text, "
            "disabled: false }. Export { createButton }. The test checks all three "
            "fields."
        ),
        "starter_code": (
            "// TODO: return { tag: 'button', textContent: text, disabled: false }\n"
            "const createButton = (text) => ({\n    tag: '', textContent: '', disabled: true\n});\n"
            "module.exports = { createButton };\n"
        ),
        "solution_code": (
            "const createButton = (text) => ({\n    tag: 'button',\n"
            "    textContent: text,\n    disabled: false\n});\n"
            "module.exports = { createButton };\n"
        ),
        "learning_objectives": [
            "Model DOM element state as plain JavaScript objects",
            "Use textContent as the DOM API defines it",
            "Return object literals from arrow functions",
        ],
        "source": mdn("Node.textContent — 'represents the text content of the node and its descendants'",
                      "https://developer.mozilla.org/en-US/docs/Web/API/Node/textContent"),
        "tests": [{
            "name": "test_create_button",
            "required": True,
            "unittest_code": (
                "const { createButton } = solution;\n"
                "const b = createButton('Click Me');\n"
                "if (b.textContent !== 'Click Me') throw new Error('Button text mismatch');\n"
                "if (b.tag !== 'button') throw new Error('Expected tag button');\n"
                "if (b.disabled !== false) throw new Error('Expected disabled false');"
            ),
        }],
    },
    "js-03": {
        "description": (
            "An async function always returns a promise, and await suspends until "
            "that promise settles. Implement `fetchUserData(userId)` as an async "
            "function resolving to { id: userId, active: true }, exported with "
            "module.exports. The test awaits it and checks both fields."
        ),
        "starter_code": (
            "// TODO: resolve { id: userId, active: true }\n"
            "async function fetchUserData(userId) {\n    return { id: 0, active: false };\n}\n"
            "module.exports = { fetchUserData };\n"
        ),
        "solution_code": (
            "async function fetchUserData(userId) {\n"
            "    return { id: userId, active: true };\n}\n"
            "module.exports = { fetchUserData };\n"
        ),
        "learning_objectives": [
            "Declare async functions that return promises",
            "Await asynchronous results in test code",
            "Resolve structured objects asynchronously",
        ],
        "source": mdn("Statements — async_function: 'An async function ... always returns a promise'",
                      "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/async_function"),
        "tests": [{
            "name": "test_async_user",
            "required": True,
            "unittest_code": (
                "const res = await solution.fetchUserData(42);\n"
                "if (res.id !== 42) throw new Error('Expected id 42');\n"
                "if (res.active !== true) throw new Error('Expected active true');"
            ),
        }],
    },
    "js-04": {
        "description": (
            "Checkpoint: implement `createServerConfig(port = 8080)` using a default "
            "parameter (default function parameters initialize named parameters when "
            "no value is passed) and return the shorthand object "
            "{ port, env: 'development' }. Tests check createServerConfig(3000).port "
            "=== 3000, createServerConfig().port === 8080, and env === 'development'."
        ),
        "starter_code": (
            "// TODO: add a default value of 8080 for port and return env 'development'\n"
            "function createServerConfig(port) {\n    return { port, env: 'production' };\n}\n"
            "module.exports = { createServerConfig };\n"
        ),
        "solution_code": (
            "function createServerConfig(port = 8080) {\n"
            "    return { port, env: 'development' };\n}\n"
            "module.exports = { createServerConfig };\n"
        ),
        "learning_objectives": [
            "Use default parameter values for optional arguments",
            "Use shorthand property names in object literals",
            "Apply core JavaScript syntax under checkpoint conditions",
        ],
        "source": mdn("Functions — Default parameters: 'allow named parameters to be initialized with default values if no value or undefined is passed'",
                      "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Functions/Default_parameters"),
        "tests": [{
            "name": "test_server_config",
            "required": True,
            "unittest_code": (
                "const cfg = solution.createServerConfig(3000);\n"
                "if (cfg.port !== 3000) throw new Error('Port mismatch');\n"
                "const dflt = solution.createServerConfig();\n"
                "if (dflt.port !== 8080) throw new Error('Expected default port 8080');\n"
                "if (cfg.env !== 'development' || dflt.env !== 'development') "
                "throw new Error(\"Expected env 'development'\");"
            ),
        }],
    },
    # ---------------- TypeScript ----------------
    "ts-01": {
        "description": (
            "TypeScript adds explicit type annotations on top of JavaScript's "
            "string, number, and boolean primitives. Implement the exported "
            "formatGreeting(name: string, isDeveloper: boolean): string so it "
            "returns 'Hello <name>' and appends ' (Dev)' only when isDeveloper is "
            "true. Tests check both branches."
        ),
        "starter_code": (
            "export function formatGreeting(name: string, isDeveloper: boolean): string {\n"
            "    // TODO: build 'Hello <name>' plus ' (Dev)' when isDeveloper\n"
            "    return '';\n}\n"
        ),
        "solution_code": (
            "export function formatGreeting(name: string, isDeveloper: boolean): string {\n"
            "    return `Hello ${name}${isDeveloper ? ' (Dev)' : ''}`;\n}\n"
        ),
        "learning_objectives": [
            "Annotate parameters and return types with lowercase primitives",
            "Use template literals with embedded ternaries",
            "Export functions from TypeScript modules",
        ],
        "source": tsh("Everyday Types — 'The primitives: string, number, and boolean'",
                      "https://www.typescriptlang.org/docs/handbook/2/everyday-types.html"),
        "tests": [{
            "name": "test_format_greeting",
            "required": True,
            "unittest_code": (
                "if (solution.formatGreeting('Alice', true) !== 'Hello Alice (Dev)')"
                " throw new Error('Dev greeting failed');\n"
                "if (solution.formatGreeting('Bob', false) !== 'Hello Bob')"
                " throw new Error('Plain greeting failed');"
            ),
        }],
    },
    "ts-02": {
        "description": (
            "Interfaces describe object shapes, and TypeScript treats a comparison "
            "like typeof input === 'number' as a type guard that narrows a union. "
            "Keep the exported User interface and implement "
            "getId(input: number | User): number: return input directly for numbers, "
            "or input.id for User objects. The test checks both union cases."
        ),
        "starter_code": (
            "export interface User {\n    id: number;\n    name: string;\n}\n\n"
            "export function getId(input: number | User): number {\n"
            "    // TODO: narrow with typeof input === 'number'\n    return 0;\n}\n"
        ),
        "solution_code": (
            "export interface User {\n    id: number;\n    name: string;\n}\n\n"
            "export function getId(input: number | User): number {\n"
            "    return typeof input === 'number' ? input : input.id;\n}\n"
        ),
        "learning_objectives": [
            "Declare object shapes with interfaces",
            "Narrow union types with typeof type guards",
            "Write functions over number | object unions",
        ],
        "source": tsh("Narrowing — typeof type guards",
                      "https://www.typescriptlang.org/docs/handbook/2/narrowing.html"),
        "tests": [{
            "name": "test_get_id",
            "required": True,
            "unittest_code": (
                "if (solution.getId(10) !== 10) throw new Error('number case failed');\n"
                "if (solution.getId({ id: 20, name: 'Bob' }) !== 20) throw new Error('User case failed');"
            ),
        }],
    },
    "ts-03": {
        "description": (
            "Generics are types which take parameters. Implement a generic class "
            "Box<T> that stores a private value field assigned in the constructor "
            "and a getValue(): T method returning it. Declare the field explicitly "
            "(constructor parameter-property shorthand is not plain erasable "
            "TypeScript). Tests build Box<number> and Box<string>."
        ),
        "starter_code": (
            "export class Box<T> {\n    private value: T;\n\n"
            "    constructor(value: T) {\n        this.value = value;\n    }\n\n"
            "    getValue(): T {\n        // TODO: return the stored value\n"
            "        throw new Error('not implemented');\n    }\n}\n"
        ),
        "solution_code": (
            "export class Box<T> {\n    private value: T;\n\n"
            "    constructor(value: T) {\n        this.value = value;\n    }\n\n"
            "    getValue(): T {\n        return this.value;\n    }\n}\n"
        ),
        "learning_objectives": [
            "Define generic classes that take a type parameter <T>",
            "Initialize class fields in the constructor",
            "Return typed values from instance methods",
        ],
        "source": tsh("Generics — 'types which take parameters'",
                      "https://www.typescriptlang.org/docs/handbook/2/generics.html"),
        "tests": [{
            "name": "test_generic_box",
            "required": True,
            "unittest_code": (
                "const n = new solution.Box<number>(42);\n"
                "if (n.getValue() !== 42) throw new Error('Box<number> failed');\n"
                "const s = new solution.Box<string>('x');\n"
                "if (s.getValue() !== 'x') throw new Error('Box<string> failed');"
            ),
        }],
    },
    "ts-04": {
        "description": (
            "Checkpoint: export interface ApiResponse<T> { data: T; status: number; } "
            "and implement the generic function wrapData<T>(data: T): ApiResponse<T> "
            "returning { data, status: 200 }. Tests wrap both a number and an object "
            "and check status plus data for each."
        ),
        "starter_code": (
            "export interface ApiResponse<T> {\n    data: T;\n    status: number;\n}\n\n"
            "export function wrapData<T>(data: T): ApiResponse<T> {\n"
            "    // TODO: return the data with status 200\n"
            "    return { data, status: 0 };\n}\n"
        ),
        "solution_code": (
            "export interface ApiResponse<T> {\n    data: T;\n    status: number;\n}\n\n"
            "export function wrapData<T>(data: T): ApiResponse<T> {\n"
            "    return { data, status: 200 };\n}\n"
        ),
        "learning_objectives": [
            "Combine interfaces and generics in API types",
            "Write generic functions with type parameters",
            "Apply TypeScript foundations under checkpoint conditions",
        ],
        "source": tsh("Generics — working with generic classes and functions",
                      "https://www.typescriptlang.org/docs/handbook/2/generics.html"),
        "tests": [{
            "name": "test_api_response_wrap",
            "required": True,
            "unittest_code": (
                "const num = solution.wrapData(5);\n"
                "if (num.status !== 200 || num.data !== 5) throw new Error('number wrap failed');\n"
                "const res = solution.wrapData({ ok: true });\n"
                "if (res.status !== 200 || !res.data.ok) throw new Error('object wrap failed');"
            ),
        }],
    },
}

# ---------------------------------------------------------------------------
# New lessons: (module file, lesson payload) — fields mirror existing schema.
# ---------------------------------------------------------------------------
NEW_JS = [
    ("basics.json", {
        "id": "js-05",
        "title": "5. Mapping Over Arrays",
        "type": "learn",
        "difficulty": "beginner",
        "duration_minutes": 5,
        "description": (
            "Array.prototype.map() returns a new array containing the results of "
            "invoking a function on every element in the calling array. Implement "
            "doubleAll(numbers) as an arrow function returning a new array with "
            "every value doubled via map, exported with module.exports. The test "
            "checks doubleAll([1, 2, 3]) produces [2, 4, 6]."
        ),
        "starter_code": (
            "// TODO: return numbers.map(n => n * 2)\n"
            "function doubleAll(numbers) {\n    return [];\n}\n"
            "module.exports = { doubleAll };\n"
        ),
        "solution_code": (
            "const doubleAll = (numbers) => numbers.map((n) => n * 2);\n"
            "module.exports = { doubleAll };\n"
        ),
        "learning_objectives": [
            "Transform every array element with map()",
            "Understand that map returns a NEW array",
            "Compose arrow functions with built-in array methods",
        ],
        "source": mdn("GlobalObjects — Array.prototype.map(): 'Returns a new array containing the results of invoking a function on every element'",
                      "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/map"),
        "tests": [{
            "name": "test_double_all",
            "required": True,
            "unittest_code": (
                "const a = solution.doubleAll([1, 2, 3]);\n"
                "if (a.join(',') !== '2,4,6') throw new Error('Expected 2,4,6');\n"
                "const empty = solution.doubleAll([]);\n"
                "if (empty.length !== 0) throw new Error('Empty array must stay empty');"
            ),
        }],
        "completion_requirements": {"required_test_names": ["test_double_all"]},
    }),
    ("async_promises.json", {
        "id": "js-06",
        "title": "6. Promise Chaining with then()",
        "type": "learn",
        "difficulty": "beginner",
        "duration_minutes": 5,
        "description": (
            "The then() method takes callback functions for the fulfilled case of a "
            "Promise and returns a new Promise. Implement getUserLabel(userId) that "
            "returns fetchUserData(userId).then(user => user.name), where the "
            "provided fetchUserData resolves { name: 'User' + userId }. Export "
            "{ getUserLabel }; the test awaits it and expects 'User7' for id 7."
        ),
        "starter_code": (
            "async function fetchUserData(userId) {\n    return { name: 'User' + userId };\n}\n\n"
            "function getUserLabel(userId) {\n"
            "    // TODO: return fetchUserData(userId).then(user => user.name)\n"
            "    return Promise.resolve('');\n}\n"
            "module.exports = { getUserLabel };\n"
        ),
        "solution_code": (
            "async function fetchUserData(userId) {\n    return { name: 'User' + userId };\n}\n\n"
            "function getUserLabel(userId) {\n"
            "    return fetchUserData(userId).then((user) => user.name);\n}\n"
            "module.exports = { getUserLabel };\n"
        ),
        "learning_objectives": [
            "Chain transformations onto promises with then()",
            "Understand that then() returns a new promise",
            "Mix async functions with explicit promise chaining",
        ],
        "source": mdn("GlobalObjects — Promise.then(): 'takes up to two arguments: callback functions for the fulfilled and rejected cases'",
                      "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/then"),
        "tests": [{
            "name": "test_promise_chain",
            "required": True,
            "unittest_code": (
                "const label = await solution.getUserLabel(7);\n"
                "if (label !== 'User7') throw new Error('Expected User7, got ' + label);"
            ),
        }],
        "completion_requirements": {"required_test_names": ["test_promise_chain"]},
    }),
    ("modules_node.json", {
        "id": "js-07",
        "title": "7. ES Modules: import & export",
        "type": "practice",
        "difficulty": "beginner",
        "duration_minutes": 8,
        "description": (
            "Modules provide top-level scoping — nothing is global unless explicitly "
            "exported. Replace the placeholders: export a const appName with the "
            "value 'Patchwork' and export a function formatTitle(title) that returns "
            "a template literal: `${title} - ${appName}` (note the hyphen and "
            "spaces). The test imports your module as an ES module."
        ),
        "starter_code": (
            "// TODO: set appName to 'Patchwork' and build the template literal\n"
            "export const appName = 'TODO';\n\n"
            "export function formatTitle(title) {\n    return title;\n}\n"
        ),
        "solution_code": (
            "export const appName = 'Patchwork';\n\n"
            "export function formatTitle(title) {\n    return `${title} - ${appName}`;\n}\n"
        ),
        "learning_objectives": [
            "Export named bindings with ES module syntax",
            "Use template literals to compose strings",
            "Know that module scope is not global scope",
        ],
        "source": mdn("Guide — JavaScript modules: 'Modules provide top-level scoping'",
                      "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Modules"),
        "tests": [{
            "name": "test_es_module_exports",
            "required": True,
            "unittest_code": (
                "if (solution.appName !== 'Patchwork') throw new Error('appName mismatch');\n"
                "if (solution.formatTitle('Learn') !== 'Learn - Patchwork')"
                " throw new Error('formatTitle mismatch');"
            ),
        }],
        "completion_requirements": {"required_test_names": ["test_es_module_exports"]},
    }),
]

NEW_TS = [
    ("relationship_types.json", {
        "id": "ts-05",
        "title": "5. Primitives and typeof Guards",
        "type": "learn",
        "difficulty": "beginner",
        "duration_minutes": 5,
        "description": (
            "JavaScript's three most common primitives are string, number, and "
            "boolean (always lowercase in TypeScript). Implement the exported "
            "describeValue(value: string | number | boolean): string that uses a "
            "typeof type guard to return exactly 'string', 'number', or 'boolean'. "
            "The test checks all three primitives."
        ),
        "starter_code": (
            "export function describeValue(value: string | number | boolean): string {\n"
            "    // TODO: narrow with typeof and return 'string' | 'number' | 'boolean'\n"
            "    return '';\n}\n"
        ),
        "solution_code": (
            "export function describeValue(value: string | number | boolean): string {\n"
            "    if (typeof value === 'number') return 'number';\n"
            "    if (typeof value === 'boolean') return 'boolean';\n"
            "    return 'string';\n}\n"
        ),
        "learning_objectives": [
            "Work with the string, number, and boolean primitives",
            "Combine unions with typeof type guards",
            "Return literal strings from exhaustive checks",
        ],
        "source": tsh("Everyday Types — 'JavaScript has three very commonly used primitives: string, number, and boolean'",
                      "https://www.typescriptlang.org/docs/handbook/2/everyday-types.html"),
        "tests": [{
            "name": "test_describe_value",
            "required": True,
            "unittest_code": (
                "if (solution.describeValue('a') !== 'string') throw new Error('string case');\n"
                "if (solution.describeValue(3) !== 'number') throw new Error('number case');\n"
                "if (solution.describeValue(false) !== 'boolean') throw new Error('boolean case');"
            ),
        }],
        "completion_requirements": {"required_test_names": ["test_describe_value"]},
    }),
    ("generics_functions.json", {
        "id": "ts-06",
        "title": "6. The Identity Function with Generics",
        "type": "learn",
        "difficulty": "beginner",
        "duration_minutes": 5,
        "description": (
            "The 'Hello World of Generics' is the identity function: a generic "
            "function identity<T>(arg: T): T that returns whatever is passed in, "
            "keeping the caller's type. Implement and export it (no type assertions "
            "needed - the parameter already has type T). The test calls it with "
            "<number> and <string>."
        ),
        "starter_code": (
            "export function identity<T>(arg: T): T {\n"
            "    // TODO: return arg\n"
            "    throw new Error('not implemented');\n}\n"
        ),
        "solution_code": (
            "export function identity<T>(arg: T): T {\n    return arg;\n}\n"
        ),
        "learning_objectives": [
            "Write a generic function with a type parameter <T>",
            "Let the caller supply (or infer) the type argument",
            "Return values typed T from generic functions",
        ],
        "source": tsh("Generics — 'Hello World of Generics' (the identity function)",
                      "https://www.typescriptlang.org/docs/handbook/2/generics.html"),
        "tests": [{
            "name": "test_identity",
            "required": True,
            "unittest_code": (
                "if (solution.identity<number>(7) !== 7) throw new Error('number identity');\n"
                "if (solution.identity<string>('x') !== 'x') throw new Error('string identity');"
            ),
        }],
        "completion_requirements": {"required_test_names": ["test_identity"]},
    }),
    ("architecture.json", {
        "id": "ts-07",
        "title": "7. Readonly Fields in Classes",
        "type": "practice",
        "difficulty": "beginner",
        "duration_minutes": 8,
        "description": (
            "Class fields may be prefixed with the readonly modifier, which "
            "prevents assignments to the field outside of the constructor. Export a "
            "class Server with `readonly port: number` initialized in the "
            "constructor and a method portAddress(): string returning "
            "`http://localhost:${this.port}`. Tests construct Server(8080) and check "
            "both the field and the address."
        ),
        "starter_code": (
            "export class Server {\n    readonly port: number;\n\n"
            "    constructor(port: number) {\n        // TODO: store the port\n"
            "        this.port = 0;\n    }\n\n"
            "    portAddress(): string {\n        // TODO: build the localhost URL\n"
            "        return '';\n    }\n}\n"
        ),
        "solution_code": (
            "export class Server {\n    readonly port: number;\n\n"
            "    constructor(port: number) {\n        this.port = port;\n    }\n\n"
            "    portAddress(): string {\n        return `http://localhost:${this.port}`;\n    }\n}\n"
        ),
        "learning_objectives": [
            "Mark class fields readonly and initialize them in the constructor",
            "Expose computed accessors as class methods",
            "Use template literals inside class methods",
        ],
        "source": tsh("Classes — readonly modifier: 'prevents assignments to the field outside of the constructor'",
                      "https://www.typescriptlang.org/docs/handbook/2/classes.html"),
        "tests": [{
            "name": "test_readonly_server",
            "required": True,
            "unittest_code": (
                "const s = new solution.Server(8080);\n"
                "if (s.port !== 8080) throw new Error('port field');\n"
                "if (s.portAddress() !== 'http://localhost:8080') throw new Error('address');"
            ),
        }],
        "completion_requirements": {"required_test_names": ["test_readonly_server"]},
    }),
]


def merge_siblings(template: dict, payload: dict, order: int) -> dict:
    """Copy section fields from the module's existing lesson template."""
    lesson = {
        "id": payload["id"],
        "title": payload["title"],
        "description": payload["description"],
        "order": order,
        "difficulty": payload["difficulty"],
        "duration_minutes": payload["duration_minutes"],
        "type": payload["type"],
        "section_id": template.get("section_id", ""),
        "section_title": template.get("section_title", ""),
        "test_out_eligible": False,
        "concepts": template.get("concepts", []),
        "prerequisites": [],
        "learning_objectives": payload["learning_objectives"],
        "source": payload["source"],
        "starter_code": payload["starter_code"],
        "solution_code": payload["solution_code"],
        "tests": payload["tests"],
        "completion_requirements": payload["completion_requirements"],
    }
    return lesson


def apply(new_lessons: list, rewrites: dict) -> None:
    files: dict[str, dict] = {}
    for module_file, payload in new_lessons:
        if module_file not in files:
            files[module_file] = {"added": []}
        files[module_file]["added"].append(payload)

    targets = sorted(JS.glob("*.json")) + sorted(TS.glob("*.json"))

    for path in targets:
        data = json.loads(path.read_text(encoding="utf-8"))
        lessons = data["lessons"]
        by_id = {l["id"]: l for l in lessons}
        changed = False
        for lid in list(by_id):
            if lid in rewrites:
                by_id[lid].update(rewrites[lid])
                changed = True
        if path.name in files:
            template = lessons[0]
            next_order = max(l.get("order", 0) for l in lessons) + 1
            for payload in files[path.name]["added"]:
                lessons.append(merge_siblings(template, payload, next_order))
                next_order += 1
                changed = True
        if changed:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    print("javascript + typescript courses rebuilt")


if __name__ == "__main__":
    apply(NEW_JS + NEW_TS, REWRITES)
