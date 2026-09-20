"""SQL course quality patch.

For all 16 sql lessons: attach SQLite official documentation sources
(every page/quote fetched and verified this session), add the missing
learning_objectives, and replace the fully-solved starter code with a
TODO skeleton that is valid SQL but fails the lesson tests (so learn
lessons are not click-through). Also convert two mastery fill_blank
exercises into proper blanks.

Run from repo root:  .venv/Scripts/python.exe backend/patch_sql_quality.py
"""
import json
from pathlib import Path

MOD = Path("curriculum/sql/modules")
SQLITE = "SQLite official documentation (sqlite.org)"
LIC = "Public domain (SQLite documentation)"

def src(name: str, url: str) -> dict:
    return {"name": f"{SQLITE} — {name}", "url": url, "license": LIC}

FIXES: dict[str, dict] = {
    "sql-01": {
        "starter_code": "-- TODO: select every column from the customers table\nSELECT id FROM customers WHERE 0;\n",
        "source": src("SELECT statements — retrieving rows", "https://sqlite.org/lang_select.html"),
    },
    "sql-02": {
        "starter_code": "-- TODO: select each country only once (duplicate rows removed)\nSELECT country FROM customers WHERE 0;\n",
        "source": src("SELECT with DISTINCT — 'duplicate rows are removed'", "https://sqlite.org/lang_select.html"),
        "learning_objectives": [
            "Project only the columns you need instead of SELECT *",
            "Remove duplicate result rows with DISTINCT",
        ],
    },
    "sql-03": {
        "starter_code": "-- TODO: select name and price of products that cost more than 100\nSELECT name, price FROM products WHERE 0;\n",
        "source": src("Expressions in WHERE clauses — BETWEEN, IN, LIKE operators", "https://sqlite.org/lang_expr.html"),
        "learning_objectives": [
            "Filter rows with WHERE and comparison operators",
            "Match sets and ranges with IN and BETWEEN",
            "Find text patterns with LIKE",
        ],
    },
    "sql-04": {
        "starter_code": "-- TODO: list product name and price, most expensive first, only the top 3\nSELECT name, price FROM products WHERE 0;\n",
        "source": src("SELECT — ORDER BY sorting and LIMIT clause", "https://sqlite.org/lang_select.html"),
        "learning_objectives": [
            "Sort result sets with ORDER BY, descending when needed",
            "Restrict result size with LIMIT",
        ],
    },
    "sql-05": {
        "starter_code": "-- TODO: insert the course (id 5, 'AI Web Apps', 'Web', 0.0) then select it back\nSELECT * FROM courses WHERE 0;\n",
        "source": src("INSERT — 'creates one or more new rows in an existing table'", "https://sqlite.org/lang_insert.html"),
        "learning_objectives": [
            "Add rows with INSERT INTO ... VALUES",
            "Modify existing rows with UPDATE ... SET ... WHERE",
            "Remove rows with DELETE FROM ... WHERE",
        ],
    },
    "sql-06": {
        "starter_code": "-- TODO: compute total revenue and average order value from orders\nSELECT 0 AS total_revenue, 0 AS avg_order WHERE 0;\n",
        "source": src("Aggregate functions — avg() 'returns the average value of all non-NULL X within a group'", "https://sqlite.org/lang_aggfunc.html"),
        "learning_objectives": [
            "Summarize a whole table with SUM(), AVG() and COUNT()",
            "Give aggregate results readable names with AS aliases",
        ],
    },
    "sql-07": {
        "starter_code": "-- TODO: count orders per customer, keeping only customers with more than one order\nSELECT customer_id, 0 AS order_count FROM orders WHERE 0 GROUP BY customer_id;\n",
        "source": src("SELECT — GROUP BY and HAVING clauses", "https://sqlite.org/lang_select.html"),
        "learning_objectives": [
            "Collapse rows into groups with GROUP BY",
            "Filter groups after aggregation with HAVING",
        ],
    },
    "sql-08": {
        "starter_code": "-- TODO: pair each customer with the total_amount of each of their orders\nSELECT c.name, o.total_amount FROM customers c JOIN orders o ON 0;\n",
        "source": src("SELECT — join operators including INNER/CROSS JOIN", "https://sqlite.org/lang_select.html"),
        "learning_objectives": [
            "Combine rows from two tables with INNER JOIN ... ON",
            "Use table aliases to keep join queries readable",
        ],
    },
    "sql-09": {
        "starter_code": "-- TODO: add a price_tier column: 'Budget' under 50, otherwise 'Premium'\nSELECT name, price FROM products WHERE 0;\n",
        "source": src("The CASE expression — WHEN/THEN/ELSE branches", "https://sqlite.org/lang_expr.html#the_case_expression"),
        "learning_objectives": [
            "Handle missing data: NULL is not a value but a marker for 'no data'",
            "Branch per row with CASE WHEN ... THEN ... ELSE ... END",
        ],
    },
    "sql-10": {
        "starter_code": "-- TODO: define a CTE named high_spenders: per-customer order totals over 100\nSELECT * FROM customers WHERE 0;\n",
        "source": src("WITH clause — 'Common Table Expressions or CTEs act like temporary views'", "https://sqlite.org/lang_with.html"),
        "learning_objectives": [
            "Name an intermediate result set with WITH ... AS (CTE)",
            "Query the CTE like a table within the same statement",
        ],
    },
    "sql-11": {
        "starter_code": "-- TODO: create table projects (id INTEGER PRIMARY KEY, title TEXT NOT NULL, budget REAL CHECK (budget >= 0))\nSELECT name FROM sqlite_master WHERE 0;\n",
        "source": src("CREATE TABLE — PRIMARY KEY, NOT NULL and CHECK constraints", "https://sqlite.org/lang_createtable.html"),
        "learning_objectives": [
            "Define tables with CREATE TABLE and typed columns",
            "Guarantee uniqueness with PRIMARY KEY",
            "Reject bad data with NOT NULL and CHECK constraints",
        ],
    },
    "sql-12": {
        "starter_code": "-- TODO: give Engineering a 5% raise inside an explicit transaction, then show the average salary\nSELECT department, AVG(salary) FROM employees WHERE 0 GROUP BY department;\n",
        "source": src("BEGIN / COMMIT / ROLLBACK — 'Transactions can be started manually using the BEGIN command'", "https://sqlite.org/lang_transaction.html"),
        "learning_objectives": [
            "Wrap multiple statements in BEGIN TRANSACTION ... COMMIT",
            "Explain atomicity: all changes apply or none do",
        ],
    },
    "sql-13": {
        "starter_code": "-- TODO: create view active_users (username, email of non-guests) and an index on users(email)\nSELECT username, email FROM users WHERE 0;\n",
        "source": src("CREATE VIEW — 'assigns a name to a pre-packaged SELECT statement'", "https://sqlite.org/lang_createview.html"),
        "learning_objectives": [
            "Store a query as a reusable view with CREATE VIEW",
            "Speed up lookups with CREATE INDEX on frequently queried columns",
        ],
    },
    "sql-14": {
        "starter_code": "-- TODO: add rank = ROW_NUMBER() OVER (PARTITION BY department ORDER BY salary DESC)\nSELECT first_name, department, salary FROM employees WHERE 0;\n",
        "source": src("Window functions — 'input values are taken from a window of one or more rows'", "https://sqlite.org/windowfunctions.html"),
        "learning_objectives": [
            "Compute per-row results without collapsing rows using OVER()",
            "Partition a window with PARTITION BY and order it with ORDER BY",
        ],
    },
    "sql-15": {
        "starter_code": "-- TODO: report each customer's name and total spent (join + group + order by total)\nSELECT c.name, 0 AS total_spent FROM customers c WHERE 0 GROUP BY c.name;\n",
        "solution_code": "SELECT c.name, SUM(o.total_amount) AS total_spent FROM customers c JOIN orders o ON c.id = o.customer_id GROUP BY c.name ORDER BY total_spent DESC;\n",
        "source": src("SELECT — joins, GROUP BY and ORDER BY for reporting queries", "https://sqlite.org/lang_select.html"),
        "learning_objectives": [
            "Chain join, aggregate, group and sort in one analytical query",
            "Order report rows by a computed aggregate",
        ],
    },
    "sql-16": {
        "starter_code": "-- TODO: left-join customers to orders and count each customer's orders\nSELECT c.name, 0 AS total_orders FROM customers c WHERE 0 GROUP BY c.name;\n",
        "solution_code": "SELECT c.name, COUNT(o.id) AS total_orders FROM customers c LEFT JOIN orders o ON c.id = o.customer_id GROUP BY c.name;\n",
        "source": src("SQL As Understood By SQLite — supported statement overview", "https://sqlite.org/lang.html"),
        "learning_objectives": [
            "Combine filtering, joining, grouping and aggregation under exam conditions",
            "Keep counting customers with zero orders via LEFT JOIN",
        ],
    },
}

EXERCISE_FIXES = {
    "sql-ex-1b": {
        "question": "Fill in the SQL keyword that retrieves data from a table: ___ * FROM customers;",
        "blanks": ["SELECT"],
        "correct_answer": ["SELECT"],
    },
    "sql-final-2": {
        "blanks": ["DISTINCT"],
        "correct_answer": ["DISTINCT"],
    },
}


def main() -> int:
    touched = 0
    ex_fixed = []
    for path in sorted(MOD.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for lesson in data["lessons"]:
            fix = FIXES.get(lesson["id"])
            if fix:
                for key, value in fix.items():
                    lesson[key] = value
                changed = True
            for sub in lesson.get("sublessons", []):
                for ex in sub.get("exercises", []):
                    if ex["id"] in EXERCISE_FIXES:
                        ex.update(EXERCISE_FIXES[ex["id"]])
                        ex_fixed.append(ex["id"])
                        changed = True
            for ex in lesson.get("mastery_exam", []) or []:
                if ex["id"] in EXERCISE_FIXES:
                    ex.update(EXERCISE_FIXES[ex["id"]])
                    ex_fixed.append(ex["id"])
                    changed = True
        if changed:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
            touched += 1
    print(f"patched {touched} module files; exercises fixed: {sorted(set(ex_fixed))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
