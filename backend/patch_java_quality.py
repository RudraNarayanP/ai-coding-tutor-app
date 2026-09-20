"""Java course quality patch: verified Oracle documentation sources for all 30
lessons, enriched the 10 thin descriptions with the exact rules the tests
check, and repaired the 3 malformed fill_blank exercises.

Every Oracle URL below was fetched and inspected this session:
- docs.oracle.com/javase/tutorial/java/nutsandbolts/{variables,operators,arrays,flow,if,for,while}.html
- docs.oracle.com/javase/tutorial/java/javaOO/{classes,methods,constructors,usingobject,accesscontrol}.html
- docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html

Run from repo root:  .venv/Scripts/python.exe backend/patch_java_quality.py
"""
import json
from pathlib import Path

MOD = Path("curriculum/java/modules")
LIC = "Oracle Free Use Terms and Conditions (documentation)"

def orc(name: str, url: str) -> dict:
    return {"name": f"Oracle Java Tutorials — {name}", "url": url, "license": LIC}

NUTS = "https://docs.oracle.com/javase/tutorial/java/nutsandbolts"
OOP = "https://docs.oracle.com/javase/tutorial/java/javaOO"

SOURCES: dict[str, dict] = {
    "java-variables-step-1": orc("Defining Methods", f"{OOP}/methods.html"),
    "java-variables-step-2": orc("Declaring and Initializing Variables (int primitives)",
                                 f"{NUTS}/variables.html"),
    "java-variables-01": orc("Operator Precedence — multiplicative and additive operators",
                             f"{NUTS}/operators.html"),
    "java-variables-practice-1": orc("Operator Precedence — multiplicative and additive operators",
                                     f"{NUTS}/operators.html"),
    "java-variables-checkpoint": orc("Operator Precedence — multiplicative and additive operators",
                                     f"{NUTS}/operators.html"),
    "java-conditionals-step-1": orc("The if-then and if-then-else Statements", f"{NUTS}/if.html"),
    "java-conditionals-step-2": orc("Operator Precedence — logical AND (&&) and OR (||), unary !",
                                    f"{NUTS}/operators.html"),
    "java-conditionals-01": orc("The if-then-else Statement", f"{NUTS}/if.html"),
    "java-conditionals-practice-1": orc("The if-then Statement (boolean expressions)",
                                        f"{NUTS}/if.html"),
    "java-conditionals-checkpoint": orc("The if-then and if-then-else Statements", f"{NUTS}/if.html"),
    "java-loops-step-1": orc("The for Statement", f"{NUTS}/for.html"),
    "java-loops-step-2": orc("The while and do-while Statements", f"{NUTS}/while.html"),
    "java-loops-01": orc("The for Statement", f"{NUTS}/for.html"),
    "java-loops-practice-1": orc("The for Statement", f"{NUTS}/for.html"),
    "java-loops-checkpoint": orc("The for Statement", f"{NUTS}/for.html"),
    "java-arrays-step-1": orc("Arrays — 'The length of an array is established when the array is created'",
                              f"{NUTS}/arrays.html"),
    "java-arrays-step-2": orc("Arrays — indexing and length", f"{NUTS}/arrays.html"),
    "java-arrays-01": orc("Arrays — for/for-each over array elements", f"{NUTS}/arrays.html"),
    "java-arrays-practice-1": orc("Arrays — indexing with brackets", f"{NUTS}/arrays.html"),
    "java-arrays-checkpoint": orc("Arrays — the enhanced for statement",
                                  f"{NUTS}/arrays.html"),
    "java-methods-step-1": orc("Overloading Methods — 'methods within a class can have the same name if "
                               "they have different parameter lists'", f"{OOP}/methods.html"),
    "java-methods-step-2": orc("Defining Methods", f"{OOP}/methods.html"),
    "java-methods-01": orc("Defining Methods — return values", f"{OOP}/methods.html"),
    "java-methods-practice-1": {
        "name": "Java SE 21 API — String.trim() and String.toLowerCase()",
        "url": "https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html",
        "license": LIC},
    "java-methods-checkpoint": orc("Defining Methods", f"{OOP}/methods.html"),
    "java-oop-step-1": orc("Providing Constructors — 'they use the name of the class and have no return type'",
                           f"{OOP}/constructors.html"),
    "java-oop-step-2": orc("Using Objects — invoke methods on object references", f"{OOP}/usingobject.html"),
    "java-oop-01": orc("Using Objects — invoke methods on object references", f"{OOP}/usingobject.html"),
    "java-oop-practice-1": orc("Controlling Access to Members of a Class (private fields)",
                               f"{OOP}/accesscontrol.html"),
    "java-oop-checkpoint": orc("Controlling Access to Members of a Class (private fields)",
                               f"{OOP}/accesscontrol.html"),
}

DESCRIPTIONS: dict[str, str] = {
    "java-conditionals-practice-1": (
        "Implement isLeapYear(int year): a year is a leap year when it is divisible by 4 "
        "but not by 100, unless it is also divisible by 400. The tests require 2000 and "
        "2024 to be leap years and 1900 to be a common year."
    ),
    "java-loops-01": (
        "Implement factorial(int n) returning n! as a long, using a loop over 1..n. "
        "Remember 0! == 1 — the tests check factorial(5) == 120 and factorial(0) == 1."
    ),
    "java-loops-practice-1": (
        "Implement isPrime(int n): values <= 1 are not prime. Trial-divide by every "
        "integer from 2 while i * i <= n; if any divides n evenly it is composite. "
        "The tests check 13 is prime and 12 is not."
    ),
    "java-loops-checkpoint": (
        "Implement countEvensInRange(int start, int end): loop from start to end "
        "inclusive and count the even numbers (i % 2 == 0). The test expects 5 evens "
        "in the range 1..10."
    ),
    "java-arrays-practice-1": (
        "Implement reverse(int[] numbers) so it reverses the array in place — swap "
        "elements from both ends while the left index stays below the right index. "
        "The test expects {1, 2, 3, 4} to become {4, 3, 2, 1}."
    ),
    "java-arrays-checkpoint": (
        "Implement contains(int[] numbers, int target): walk the array (a for-each loop "
        "fits nicely) and return true only when target appears. The test expects "
        "contains({5, 10, 15}, 10) == true and contains({5, 10, 15}, 99) == false."
    ),
    "java-methods-practice-1": (
        "Implement sanitize(String input): remove leading/trailing whitespace with "
        "trim() and convert to lowercase with toLowerCase() — return \"\" for null "
        "input. The test expects sanitize(\"  JAVA  \") to equal \"java\"."
    ),
    "java-methods-checkpoint": (
        "Implement power(int base, int exponent) returning base raised to exponent as "
        "an int — e.g. Math.pow with an int cast, or a multiplying loop. The test "
        "expects power(2, 3) == 8."
    ),
    "java-oop-practice-1": (
        "Student is an encapsulated record: private name and score fields set by the "
        "constructor. Implement isPassing() to return true when this.score >= 60. "
        "The test creates new Student(\"Ada\", 85) and expects isPassing() == true."
    ),
    "java-oop-checkpoint": (
        "Rectangle keeps private width/height fields initialized by the constructor. "
        "Implement getArea() to return this.width * this.height. The test expects "
        "new Rectangle(4.0, 5.0).getArea() == 20.0 (within 0.001)."
    ),
}

EXERCISE_FIXES = {
    "java-ex-1b": {"correct_answer": ["\"Java\""]},
    "java-exam-2": {
        "question": "Type the Java String literal for Java: String lang = ___;",
        "blanks": ["\"Java\""],
        "correct_answer": ["\"Java\""],
    },
    "java-chk-2": {
        "blanks": ["int"],
        "correct_answer": ["int"],
    },
}


def main() -> int:
    touched = 0
    ex_fixed = []
    for path in sorted(MOD.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for lesson in data["lessons"]:
            lid = lesson["id"]
            if lid in SOURCES and not (lesson.get("source") or {}).get("url"):
                lesson["source"] = SOURCES[lid]
                changed = True
            if lid in DESCRIPTIONS:
                lesson["description"] = DESCRIPTIONS[lid]
                changed = True
            def handle(ex):
                nonlocal changed
                if ex["id"] in EXERCISE_FIXES:
                    ex.update(EXERCISE_FIXES[ex["id"]])
                    ex_fixed.append(ex["id"])
                    changed = True
            for sub in lesson.get("sublessons", []):
                for ex in sub.get("exercises", []):
                    handle(ex)
            for ex in lesson.get("mastery_exam", []) or []:
                handle(ex)
        if changed:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
            touched += 1
    print(f"patched {touched} java modules; exercises fixed: {sorted(set(ex_fixed))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
