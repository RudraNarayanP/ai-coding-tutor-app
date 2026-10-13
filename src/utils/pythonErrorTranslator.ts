/**
 * Utility to translate Python runtime/syntax errors into plain English for beginners.
 */
export function translatePythonError(rawError: string): { summary: string; detail: string } {
  if (!rawError) return { summary: 'An unknown error occurred.', detail: '' }

  const clean = rawError.trim()

  if (clean.includes('SyntaxError')) {
    if (clean.includes("invalid syntax")) {
      return {
        summary: "SyntaxError: Python couldn't understand this line. Check for a missing colon `:`, unmatched parentheses `()`, or a typo.",
        detail: clean,
      }
    }
    if (clean.includes("expected ':'") || clean.includes("colon")) {
      return {
        summary: "SyntaxError: You're missing a colon `:` at the end of a statement (like an `if`, `def`, or `for`).",
        detail: clean,
      }
    }
    return {
      summary: "SyntaxError: Check your code structure, colons, or punctuation.",
      detail: clean,
    }
  }

  if (clean.includes('IndentationError')) {
    return {
      summary: "IndentationError: Python relies on indentation! Check that your code blocks are aligned with 4 spaces.",
      detail: clean,
    }
  }

  if (clean.includes('NameError')) {
    const match = clean.match(/name '([^']+)' is not defined/)
    const name = match ? match[1] : 'a variable'
    return {
      summary: `NameError: You used \`${name}\` before creating or defining it. Check for typos!`,
      detail: clean,
    }
  }

  if (clean.includes('TypeError')) {
    return {
      summary: "TypeError: You tried to perform an operation on incompatible types (like adding a string to an integer).",
      detail: clean,
    }
  }

  if (clean.includes('ZeroDivisionError')) {
    return {
      summary: "ZeroDivisionError: You tried to divide a number by zero `0`, which math doesn't allow!",
      detail: clean,
    }
  }

  return {
    summary: clean.split('\n')[0] || "Execution error",
    detail: clean,
  }
}
