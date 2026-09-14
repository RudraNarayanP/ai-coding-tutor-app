from backend.materials import Material, CompanionQuestion

MATERIALS: list[Material] = [
    # ─── PYTHON ─────────────────────────────────────────────────────────────
    Material(
        id="python-tutor-visualizer",
        title="Python Tutor — Code Execution Visualizer",
        description="See step-by-step how Python allocates variables, stack frames, and objects in memory.",
        language="python",
        category="visualization",
        difficulty="beginner",
        resource_type="visualizer",
        url="https://pythontutor.com/",
        official_or_community="community",
        estimated_minutes=3,
        concept_tags=["variables", "loops", "functions", "lists", "dictionaries", "call_stack"],
        recommended_stage="visualize",
        xp_reward=15,
        completion_type="companion_question",
        source_domain="pythontutor.com",
        is_external=True,
        is_interactive=True,
        is_visualizer=True,
        companion_question=CompanionQuestion(
            question="What happens to a local variable in Python Tutor's stack view when its enclosing function returns?",
            options=[
                "Its frame is popped off the call stack and removed",
                "It stays in memory permanently",
                "It automatically converts into a global variable",
                "It is printed to stdout"
            ],
            correct_answer="Its frame is popped off the call stack and removed",
            explanation="When a function finishes executing, its frame is removed from the call stack."
        )
    ),
    Material(
        id="automate-boring-stuff",
        title="Automate the Boring Stuff with Python",
        description="Practical Python guide for automating file handling, spreadsheets, text processing, and daily tasks.",
        language="python",
        category="automation",
        difficulty="beginner",
        resource_type="tutorial",
        url="https://automatetheboringstuff.com/",
        official_or_community="community",
        estimated_minutes=10,
        concept_tags=["files", "automation", "text_processing", "spreadsheets"],
        recommended_stage="build",
        xp_reward=20,
        completion_type="companion_question",
        source_domain="automatetheboringstuff.com",
        is_external=True,
        is_project=True,
        companion_question=CompanionQuestion(
            question="In Python automation scripts, which module is standard for cross-platform file path manipulation?",
            options=[
                "pathlib (or os.path)",
                "sys.argv",
                "math",
                "json"
            ],
            correct_answer="pathlib (or os.path)",
            explanation="pathlib and os.path safely handle directory separators across Windows, macOS, and Linux."
        )
    ),
    Material(
        id="kaggle-learn-python",
        title="Kaggle Learn Python",
        description="Hands-on Python tutorial covering syntax, data structures, and foundational libraries.",
        language="python",
        category="fundamentals",
        difficulty="beginner",
        resource_type="tutorial",
        url="https://www.kaggle.com/learn/python",
        official_or_community="community",
        estimated_minutes=8,
        concept_tags=["syntax", "functions", "booleans", "conditionals", "lists"],
        recommended_stage="practice",
        xp_reward=15,
        completion_type="companion_question",
        source_domain="kaggle.com",
        is_external=True,
        is_interactive=True,
        companion_question=CompanionQuestion(
            question="In Python list comprehensions, what is the correct syntax to filter even numbers from a list called numbers?",
            options=[
                "[x for x in numbers if x % 2 == 0]",
                "[for x in numbers filter x % 2 == 0]",
                "[x if x % 2 == 0 in numbers]",
                "[x for x in numbers where x % 2 == 0]"
            ],
            correct_answer="[x for x in numbers if x % 2 == 0]",
            explanation="List comprehensions use '[expression for item in iterable if condition]'."
        )
    ),

    # ─── C++ ────────────────────────────────────────────────────────────────
    Material(
        id="learncpp-fundamentals",
        title="LearnCpp — C++ Tutorial Guide",
        description="Comprehensive, modern C++ tutorials covering fundamentals, memory, pointers, and OOP.",
        language="cpp",
        category="fundamentals",
        difficulty="beginner",
        resource_type="documentation",
        url="https://www.learncpp.com/",
        official_or_community="community",
        estimated_minutes=7,
        concept_tags=["cpp_basics", "functions", "pointers", "references", "classes"],
        recommended_stage="learn",
        xp_reward=15,
        completion_type="companion_question",
        source_domain="learncpp.com",
        is_external=True,
        is_reference=True,
        companion_question=CompanionQuestion(
            question="In C++, what is a primary advantage of passing large objects by const reference (const T&) vs value?",
            options=[
                "It avoids expensive object copies while preventing modifications",
                "It makes passing values faster on 8-bit CPUs",
                "It converts the object into a global variable",
                "There is no difference in C++"
            ],
            correct_answer="It avoids expensive object copies while preventing modifications",
            explanation="Passing by const reference avoids copying memory while guaranteeing read-only safety."
        )
    ),
    Material(
        id="compiler-explorer-godbolt",
        title="Compiler Explorer (Godbolt)",
        description="Interactive assembly output visualizer for C++ code across different compilers and optimization levels.",
        language="cpp",
        category="visualization",
        difficulty="intermediate",
        resource_type="playground",
        url="https://godbolt.org/",
        official_or_community="community",
        estimated_minutes=5,
        concept_tags=["compilation", "assembly", "optimization", "performance"],
        recommended_stage="visualize",
        xp_reward=20,
        completion_type="companion_question",
        source_domain="godbolt.org",
        is_external=True,
        is_interactive=True,
        is_visualizer=True,
        companion_question=CompanionQuestion(
            question="When enabling optimization flags like -O2 in Compiler Explorer, what often happens to small inline functions?",
            options=[
                "They are inlined directly into the caller, eliminating call overhead",
                "They are deleted completely from the binary",
                "They are executed slowly in interpreted mode",
                "They are converted to Python code"
            ],
            correct_answer="They are inlined directly into the caller, eliminating call overhead",
            explanation="Optimizing compilers inline short function calls directly to avoid stack frame overhead."
        )
    ),
    Material(
        id="cppreference-std",
        title="cppreference.com — C++ Standard Library Reference",
        description="The authoritative reference for C++ language syntax and standard library (STL) containers.",
        language="cpp",
        category="reference",
        difficulty="intermediate",
        resource_type="reference",
        url="https://en.cppreference.com/",
        official_or_community="community",
        estimated_minutes=5,
        concept_tags=["std_vector", "stl", "cpp_reference"],
        recommended_stage="review",
        xp_reward=15,
        completion_type="companion_question",
        source_domain="cppreference.com",
        is_external=True,
        is_reference=True,
        companion_question=CompanionQuestion(
            question="What is the amortized time complexity of std::vector::push_back in C++?",
            options=[
                "Amortized O(1)",
                "O(N)",
                "O(log N)",
                "O(N^2)"
            ],
            correct_answer="Amortized O(1)",
            explanation="Appending to a std::vector is amortized O(1) because capacity doubles when reallocating."
        )
    ),
    Material(
        id="cpp-core-guidelines",
        title="C++ Core Guidelines",
        description="Best practices for modern C++ safety, resource management, and pointer usage by Bjarne Stroustrup.",
        language="cpp",
        category="architecture",
        difficulty="advanced",
        resource_type="documentation",
        url="https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines",
        official_or_community="official",
        estimated_minutes=8,
        concept_tags=["ownership", "resource_management", "smart_pointers", "modern_cpp"],
        recommended_stage="build",
        xp_reward=20,
        completion_type="companion_question",
        source_domain="isocpp.github.io",
        is_external=True,
        is_reference=True,
        companion_question=CompanionQuestion(
            question="According to C++ Core Guidelines, which smart pointer expresses exclusive ownership?",
            options=[
                "std::unique_ptr",
                "std::shared_ptr",
                "std::weak_ptr",
                "raw pointer"
            ],
            correct_answer="std::unique_ptr",
            explanation="std::unique_ptr explicitly represents single/exclusive ownership of a resource."
        )
    ),

    # ─── JAVA ───────────────────────────────────────────────────────────────
    Material(
        id="helsinki-java-mooc",
        title="University of Helsinki Java Programming MOOC",
        description="World-renowned introductory Java course focusing on object-oriented programming concepts.",
        language="java",
        category="fundamentals",
        difficulty="beginner",
        resource_type="tutorial",
        url="https://java-programming.mooc.fi/",
        official_or_community="official",
        estimated_minutes=10,
        concept_tags=["java_basics", "oop", "classes", "collections"],
        recommended_stage="learn",
        xp_reward=20,
        completion_type="companion_question",
        source_domain="java-programming.mooc.fi",
        is_external=True,
        is_interactive=True,
        companion_question=CompanionQuestion(
            question="In Java OOP, what keyword is used by a subclass constructor to invoke a constructor in its parent class?",
            options=[
                "super()",
                "this()",
                "parent()",
                "extends()"
            ],
            correct_answer="super()",
            explanation="super() invokes the superclass constructor from within a subclass constructor."
        )
    ),
    Material(
        id="oracle-java-tutorials",
        title="Oracle Java Tutorials & Dev.java",
        description="Official documentation and guides covering Java language basics, OOP, and collections.",
        language="java",
        category="reference",
        difficulty="beginner",
        resource_type="documentation",
        url="https://docs.oracle.com/javase/tutorial/java/",
        official_or_community="official",
        estimated_minutes=7,
        concept_tags=["exceptions", "collections", "interfaces", "generics"],
        recommended_stage="practice",
        xp_reward=15,
        completion_type="companion_question",
        source_domain="docs.oracle.com",
        is_external=True,
        is_reference=True,
        companion_question=CompanionQuestion(
            question="Which Java interface hierarchy is root for single-element collections like List and Set?",
            options=[
                "java.util.Collection",
                "java.util.Map",
                "java.util.Stream",
                "java.lang.Object"
            ],
            correct_answer="java.util.Collection",
            explanation="java.util.Collection is the root interface in the Java collections framework."
        )
    ),
    Material(
        id="oracle-academy-java",
        title="Oracle Academy Java Curriculum",
        description="Structured curriculum path for Java foundations and OOP progression.",
        language="java",
        category="fundamentals",
        difficulty="intermediate",
        resource_type="reference",
        url="https://academy.oracle.com/en/solutions-curriculum-java.html",
        official_or_community="official",
        estimated_minutes=8,
        concept_tags=["foundations", "architecture", "java_se"],
        recommended_stage="review",
        xp_reward=15,
        completion_type="companion_question",
        source_domain="academy.oracle.com",
        is_external=True,
        is_reference=True,
        companion_question=CompanionQuestion(
            question="What is a primary advantage of compiling Java code into bytecode for execution on the JVM?",
            options=[
                "Platform independence ('write once, run anywhere')",
                "Direct hardware execution without JVM runtime",
                "Automatic conversion to C++ binaries",
                "Disabling garbage collection"
            ],
            correct_answer="Platform independence ('write once, run anywhere')",
            explanation="Java bytecode runs on any system with a compatible Java Virtual Machine (JVM)."
        )
    ),

    # ─── JAVASCRIPT ─────────────────────────────────────────────────────────
    Material(
        id="javascript-info",
        title="JavaScript.info — The Modern JavaScript Tutorial",
        description="Detailed guide to modern JavaScript from foundational variables to async/await and promises.",
        language="javascript",
        category="fundamentals",
        difficulty="beginner",
        resource_type="tutorial",
        url="https://javascript.info/",
        official_or_community="community",
        estimated_minutes=8,
        concept_tags=["js_basics", "promises", "async_await", "modules"],
        recommended_stage="learn",
        xp_reward=15,
        completion_type="companion_question",
        source_domain="javascript.info",
        is_external=True,
        is_reference=True,
        companion_question=CompanionQuestion(
            question="In JavaScript, what does await do when placed before a Promise inside an async function?",
            options=[
                "Pauses async function execution until the Promise resolves or rejects",
                "Blocks the browser thread completely",
                "Cancels the promise execution",
                "Converts the promise into a string"
            ],
            correct_answer="Pauses async function execution until the Promise resolves or rejects",
            explanation="await pauses execution of the async function non-blockingly until the Promise settles."
        )
    ),
    Material(
        id="mdn-web-docs",
        title="MDN Web Docs — JavaScript Reference",
        description="The web platform benchmark reference for JavaScript syntax, DOM manipulation, and Web APIs.",
        language="javascript",
        category="reference",
        difficulty="beginner",
        resource_type="documentation",
        url="https://developer.mozilla.org/",
        official_or_community="official",
        estimated_minutes=5,
        concept_tags=["dom", "events", "fetch", "browser_apis"],
        recommended_stage="reference",
        xp_reward=15,
        completion_type="companion_question",
        source_domain="developer.mozilla.org",
        is_external=True,
        is_reference=True,
        companion_question=CompanionQuestion(
            question="Which method on document selects the first DOM element matching a CSS selector?",
            options=[
                "document.querySelector()",
                "document.getElementById()",
                "document.find()",
                "document.getElementBySelector()"
            ],
            correct_answer="document.querySelector()",
            explanation="document.querySelector() returns the first element matching a CSS selector string."
        )
    ),
    Material(
        id="frontend-mentor",
        title="Frontend Mentor — Real Web Challenges",
        description="Realistic UI building challenges to hone HTML, CSS, and JavaScript implementation skills.",
        language="javascript",
        category="projects",
        difficulty="intermediate",
        resource_type="project",
        url="https://www.frontendmentor.io/",
        official_or_community="community",
        estimated_minutes=12,
        concept_tags=["frontend", "responsive_ui", "projects"],
        recommended_stage="build",
        xp_reward=25,
        completion_type="companion_question",
        source_domain="frontendmentor.io",
        is_external=True,
        is_project=True,
        companion_question=CompanionQuestion(
            question="What is an essential practice when building responsive web layouts?",
            options=[
                "Use CSS Flexbox/Grid and media queries",
                "Hardcode pixel widths for all elements",
                "Disable mobile viewport scaling",
                "Use inline styles exclusively"
            ],
            correct_answer="Use CSS Flexbox/Grid and media queries",
            explanation="Flexbox, Grid, and media queries allow layouts to adapt fluidly across screen sizes."
        )
    ),
    Material(
        id="chrome-devtools-docs",
        title="Chrome DevTools Documentation",
        description="Guide to debugging JavaScript, setting breakpoints, and inspecting Network activity.",
        language="javascript",
        category="debugging",
        difficulty="beginner",
        resource_type="tutorial",
        url="https://developer.chrome.com/docs/devtools/",
        official_or_community="official",
        estimated_minutes=5,
        concept_tags=["debugging", "console", "network_tab", "breakpoints"],
        recommended_stage="try",
        xp_reward=15,
        completion_type="companion_question",
        source_domain="developer.chrome.com",
        is_external=True,
        is_interactive=True,
        companion_question=CompanionQuestion(
            question="How do you pause JavaScript execution at a specific line in Chrome DevTools?",
            options=[
                "Click the line number in the Sources panel to set a breakpoint",
                "Close the browser window",
                "Add a console.log statement",
                "Refresh the page repeatedly"
            ],
            correct_answer="Click the line number in the Sources panel to set a breakpoint",
            explanation="Clicking a line number in the Sources panel creates a breakpoint that pauses execution."
        )
    ),

    # ─── SQL ────────────────────────────────────────────────────────────────
    Material(
        id="sqlbolt-interactive",
        title="SQLBolt — Interactive SQL Lessons",
        description="Step-by-step interactive SQL tutorials covering queries, filtering, joins, and table modifications.",
        language="sql",
        category="fundamentals",
        difficulty="beginner",
        resource_type="interactive",
        url="https://sqlbolt.com/",
        official_or_community="community",
        estimated_minutes=8,
        concept_tags=["select", "where", "joins", "aggregation"],
        recommended_stage="learn",
        xp_reward=15,
        completion_type="companion_question",
        source_domain="sqlbolt.com",
        is_external=True,
        is_interactive=True,
        companion_question=CompanionQuestion(
            question="In SQL query execution order, which clause is evaluated BEFORE SELECT?",
            options=[
                "FROM and WHERE",
                "ORDER BY",
                "LIMIT",
                "UNION"
            ],
            correct_answer="FROM and WHERE",
            explanation="SQL processes FROM and WHERE clauses to identify data before executing SELECT."
        )
    ),
    Material(
        id="sqlzoo-tutorials",
        title="SQLZoo — SQL Exercises & Quizzes",
        description="Interactive SQL reference and practice problems for SELECT, JOINs, and Window functions.",
        language="sql",
        category="practice",
        difficulty="intermediate",
        resource_type="interactive",
        url="https://www.sqlzoo.net/wiki/SQL_Tutorial",
        official_or_community="community",
        estimated_minutes=8,
        concept_tags=["joins", "subqueries", "window_functions", "null"],
        recommended_stage="practice",
        xp_reward=20,
        completion_type="companion_question",
        source_domain="sqlzoo.net",
        is_external=True,
        is_interactive=True,
        companion_question=CompanionQuestion(
            question="Which JOIN type returns all rows from the left table even if there are no matches in the right table?",
            options=[
                "LEFT JOIN (or LEFT OUTER JOIN)",
                "INNER JOIN",
                "RIGHT JOIN",
                "CROSS JOIN"
            ],
            correct_answer="LEFT JOIN (or LEFT OUTER JOIN)",
            explanation="LEFT JOIN preserves all rows from the left table, filling missing right-side values with NULL."
        )
    ),
    Material(
        id="mode-sql-tutorial",
        title="Mode SQL Tutorial for Data Analytics",
        description="Practical SQL analytics guide focusing on real business questions, aggregation, and case statements.",
        language="sql",
        category="analytics",
        difficulty="intermediate",
        resource_type="tutorial",
        url="https://mode.com/sql-tutorial/",
        official_or_community="community",
        estimated_minutes=10,
        concept_tags=["analytics", "group_by", "case_when", "reporting"],
        recommended_stage="try",
        xp_reward=20,
        completion_type="companion_question",
        source_domain="mode.com",
        is_external=True,
        is_interactive=True,
        companion_question=CompanionQuestion(
            question="Which SQL clause is used to filter aggregate results generated by GROUP BY?",
            options=[
                "HAVING",
                "WHERE",
                "ORDER BY",
                "DISTINCT"
            ],
            correct_answer="HAVING",
            explanation="WHERE filters rows before aggregation, while HAVING filters group aggregates."
        )
    ),
    Material(
        id="datalemur-sql",
        title="DataLemur — SQL Interview Practice",
        description="Real-world SQL interview problems and query challenges for data engineering and analytics.",
        language="sql",
        category="challenges",
        difficulty="advanced",
        resource_type="challenge",
        url="https://datalemur.com/",
        official_or_community="community",
        estimated_minutes=12,
        concept_tags=["interview_prep", "queries", "real_world_sql"],
        recommended_stage="challenge",
        xp_reward=25,
        completion_type="companion_question",
        source_domain="datalemur.com",
        is_external=True,
        is_challenge=True,
        companion_question=CompanionQuestion(
            question="What does COUNT(DISTINCT user_id) calculate in an analytics SQL query?",
            options=[
                "The number of unique user IDs",
                "The total row count including duplicates",
                "The maximum user ID value",
                "The sum of user IDs"
            ],
            correct_answer="The number of unique user IDs",
            explanation="COUNT(DISTINCT column) counts distinct non-null values."
        )
    ),

    # ─── TYPESCRIPT ─────────────────────────────────────────────────────────
    Material(
        id="ts-handbook",
        title="TypeScript Handbook",
        description="Official guide to TypeScript types, interfaces, generics, narrowing, and type manipulation.",
        language="typescript",
        category="fundamentals",
        difficulty="beginner",
        resource_type="documentation",
        url="https://www.typescriptlang.org/docs/handbook/intro",
        official_or_community="official",
        estimated_minutes=8,
        concept_tags=["types", "interfaces", "generics", "unions"],
        recommended_stage="learn",
        xp_reward=15,
        completion_type="companion_question",
        source_domain="typescriptlang.org",
        is_external=True,
        is_reference=True,
        companion_question=CompanionQuestion(
            question="What is a key difference between an interface and a type alias for objects in TypeScript?",
            options=[
                "Interfaces support declaration merging, whereas type aliases cannot be reopened",
                "Types can only represent numbers",
                "Interfaces only exist at runtime",
                "Types do not support union types"
            ],
            correct_answer="Interfaces support declaration merging, whereas type aliases cannot be reopened",
            explanation="Interfaces in TS can be merged across multiple declarations, unlike type aliases."
        )
    ),
    Material(
        id="ts-playground",
        title="TypeScript Playground",
        description="Interactive browser environment to experiment with TypeScript type inference and compiler output.",
        language="typescript",
        category="visualization",
        difficulty="beginner",
        resource_type="playground",
        url="https://www.typescriptlang.org/play",
        official_or_community="official",
        estimated_minutes=5,
        concept_tags=["playground", "type_inference", "compiler_options"],
        recommended_stage="visualize",
        xp_reward=15,
        completion_type="companion_question",
        source_domain="typescriptlang.org",
        is_external=True,
        is_interactive=True,
        is_visualizer=True,
        companion_question=CompanionQuestion(
            question="Does TypeScript type checking happen at compile time or at runtime?",
            options=[
                "Compile time only; type annotations are erased in JS output",
                "Runtime only",
                "Both compile time and runtime",
                "Neither"
            ],
            correct_answer="Compile time only; type annotations are erased in JS output",
            explanation="TypeScript types are purely compile-time constructs and are stripped during compilation."
        )
    ),
    Material(
        id="type-challenges",
        title="Type Challenges — Advanced Type Manipulation",
        description="Collection of TypeScript type-system puzzles for mastering generics and conditional types.",
        language="typescript",
        category="challenges",
        difficulty="advanced",
        resource_type="challenge",
        url="https://github.com/type-challenges/type-challenges",
        official_or_community="community",
        estimated_minutes=12,
        concept_tags=["generics", "utility_types", "advanced_types"],
        recommended_stage="challenge",
        xp_reward=25,
        completion_type="companion_question",
        source_domain="github.com",
        is_external=True,
        is_challenge=True,
        companion_question=CompanionQuestion(
            question="Which TypeScript built-in utility type constructs a type with all properties of T marked as optional?",
            options=[
                "Partial<T>",
                "Required<T>",
                "Readonly<T>",
                "Pick<T>"
            ],
            correct_answer="Partial<T>",
            explanation="Partial<T> returns a new type where all properties of T are optional."
        )
    ),
    Material(
        id="total-typescript",
        title="Total TypeScript",
        description="Practical TypeScript guides and patterns for professional software development.",
        language="typescript",
        category="practice",
        difficulty="intermediate",
        resource_type="tutorial",
        url="https://www.totaltypescript.com/",
        official_or_community="community",
        estimated_minutes=10,
        concept_tags=["practical_ts", "generics", "architecture"],
        recommended_stage="practice",
        xp_reward=20,
        completion_type="companion_question",
        source_domain="totaltypescript.com",
        is_external=True,
        companion_question=CompanionQuestion(
            question="In TypeScript generic constraints <T extends string>, what constraint is enforced on T?",
            options=[
                "T must be assignable to string",
                "T is converted to string at runtime",
                "T must be a class extending String",
                "T is optional"
            ],
            correct_answer="T must be assignable to string",
            explanation="'extends' in generic constraints limits T to types assignable to the constraint type."
        )
    )
]
