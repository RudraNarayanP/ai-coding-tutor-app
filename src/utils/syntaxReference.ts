export interface SyntaxEntry {
  concept: string
  syntax: string
  description: string
  example: string
}

export const SYNTAX_REFERENCE: Record<string, SyntaxEntry[]> = {
  python: [
    {
      concept: "Variable Assignment",
      syntax: "variable_name = value",
      description: "Assigns a value to a named variable in memory.",
      example: "x = 42\nname = 'Alice'",
    },
    {
      concept: "Function Definition",
      syntax: "def function_name(param1, param2):\n    return result",
      description: "Defines a reusable block of code that takes arguments and returns a value.",
      example: "def add(a, b):\n    return a + b",
    },
    {
      concept: "Conditional Branching",
      syntax: "if condition:\n    ...\nelif other_condition:\n    ...\nelse:\n    ...",
      description: "Executes code blocks conditionally based on boolean evaluations.",
      example: "if score >= 90:\n    print('Grade A')\nelse:\n    print('Pass')",
    },
    {
      concept: "List Comprehension",
      syntax: "[expression for item in iterable if condition]",
      description: "Concise syntax to construct a new list by transforming an existing iterable.",
      example: "squares = [x**2 for x in range(5)]",
    },
  ],
  cpp: [
    {
      concept: "Variable Declaration",
      syntax: "type variable_name = value;",
      description: "Declares a statically typed variable in C++.",
      example: "int score = 100;\nstd::string name = \"Bob\";",
    },
    {
      concept: "Function Definition",
      syntax: "return_type function_name(type param1) {\n    return value;\n}",
      description: "Defines a typed function in C++.",
      example: "int square(int x) {\n    return x * x;\n}",
    },
  ],
  javascript: [
    {
      concept: "Variable Declaration",
      syntax: "const name = value; // or let",
      description: "Declares block-scoped constants or variables.",
      example: "const count = 10;\nlet greeting = 'Hello';",
    },
    {
      concept: "Arrow Functions",
      syntax: "const fn = (a, b) => a + b;",
      description: "Shorthand syntax for anonymous function expressions.",
      example: "const double = x => x * 2;",
    },
  ],
  typescript: [
    {
      concept: "Interface Definition",
      syntax: "interface User {\n  id: number;\n  name: string;\n}",
      description: "Defines object structural types and contracts.",
      example: "interface Item { price: number; }",
    },
    {
      concept: "Type Annotations",
      syntax: "const age: number = 25;",
      description: "Attaches static type information to variables and parameters.",
      example: "function greet(name: string): string { return 'Hi ' + name; }",
    },
  ],
  sql: [
    {
      concept: "SELECT Query",
      syntax: "SELECT col1, col2 FROM table_name WHERE condition;",
      description: "Queries rows and columns from a relational table.",
      example: "SELECT name, email FROM users WHERE role = 'admin';",
    },
  ],
}
