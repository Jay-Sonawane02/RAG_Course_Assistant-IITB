"""
Claude API tool-use schemas. Kept separate from the tool implementations
(query_database.py, search_syllabi.py) so the schema -- what the LLM sees --
is easy to review independently of the execution logic.
"""

SEARCH_SYLLABI_SCHEMA = {
    "name": "search_syllabi",
    "description": (
        "Semantic search over course syllabus content. Use this when the "
        "student describes a TOPIC or INTEREST but does not already know "
        "which specific course covers it (e.g. 'which courses cover deep "
        "learning', 'anything about cryptography'). Do NOT use this if the "
        "student already names a specific course code or exact title -- use "
        "query_database instead for a direct, reliable lookup.\n\n"
        "IMPORTANT: results are ranked by semantic similarity, not topical "
        "correctness -- a query for 'security courses' can surface general "
        "networking courses that happen to be semantically nearby without "
        "actually being about security. After getting results, check each "
        "course's actual content before including it in your answer -- "
        "don't just present the raw ranked list. Exclude a result if its "
        "connection to the query is only tangential."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Natural-language description of the topic to search for, "
                    "e.g. 'transformers and attention mechanisms' or "
                    "'network security fundamentals'."
                ),
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return.",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}

QUERY_DATABASE_SCHEMA = {
    "name": "query_database",
    "description": (
        "Runs a read-only SQL SELECT query against the course database. Use "
        "whenever the student names a specific course (by code or exact "
        "title), asks about structured facts (instructor, credits, "
        "prerequisites, duration, department, UG/PG level), or asks anything "
        "requiring grade statistics (averages, pass rates, easiest/hardest "
        "courses, grade distributions).\n\n"
        "Schema:\n\n"
        "CREATE TABLE courses (\n"
        "  course_code TEXT PRIMARY KEY,\n"
        "  title TEXT NOT NULL,\n"
        "  department TEXT NOT NULL,\n"
        "  home_page TEXT,\n"
        "  autumn_instructor TEXT,\n"
        "  spring_instructor TEXT,\n"
        "  semester TEXT,             -- 'Autumn', 'Spring', or 'Autumn, Spring'\n"
        "  credits REAL,\n"
        "  prerequisites TEXT,\n"
        "  duration TEXT,\n"
        "  course_type TEXT,\n"
        "  syllabus_text TEXT,\n"
        "  references_text TEXT,\n"
        "  source_url TEXT NOT NULL,\n"
        "  last_updated TEXT NOT NULL,\n"
        "  level TEXT                 -- 'UG' or 'PG'\n"
        ");\n\n"
        "CREATE TABLE grade_distributions (\n"
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
        "  course_code TEXT NOT NULL REFERENCES courses(course_code),\n"
        "  grade TEXT NOT NULL,       -- e.g. 'AA', 'AB', 'BB', 'FR', 'AU'\n"
        "  student_count INTEGER NOT NULL\n"
        ");\n\n"
        "CREATE TABLE grade_points (\n"
        "  grade TEXT PRIMARY KEY,\n"
        "  points REAL,               -- NULL if not counted (audit/incomplete/withdrawn)\n"
        "  is_pass INTEGER\n"
        ");\n\n"
        "To compute a course's average grade point: JOIN grade_distributions "
        "to grade_points ON grade, filter WHERE points IS NOT NULL, compute a "
        "student_count-weighted average. Do not guess grade-point values "
        "yourself -- always join against grade_points.\n\n"
        "Use exactly this pattern for grade-point averages (copy it, do not "
        "reconstruct it from scratch each time -- reconstructing it "
        "differently has produced incorrect, inconsistent results):\n\n"
        "SELECT gd.course_code, c.title,\n"
        "       ROUND(SUM(gd.student_count * gp.points) * 1.0 / SUM(gd.student_count), 2) AS avg_points,\n"
        "       SUM(gd.student_count) AS total_students\n"
        "FROM grade_distributions gd\n"
        "JOIN grade_points gp ON gd.grade = gp.grade\n"
        "JOIN courses c ON gd.course_code = c.course_code\n"
        "WHERE gp.points IS NOT NULL AND gd.course_code IN (...)\n"
        "GROUP BY gd.course_code\n"
        "ORDER BY avg_points DESC\n\n"
        "Only SELECT statements are permitted. Filter to specific "
        "course_code(s) or a reasonable LIMIT."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "A single read-only SELECT statement.",
            }
        },
        "required": ["sql"],
    },
}

ALL_TOOL_SCHEMAS = [SEARCH_SYLLABI_SCHEMA, QUERY_DATABASE_SCHEMA]