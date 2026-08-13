"""
The actual agent loop. Sends the conversation to Claude with both tool
schemas attached; if Claude calls a tool, executes it locally and feeds the
result back, repeating until Claude produces a final text answer instead of
another tool call. This is what makes multi-step questions work (e.g.
search_syllabi to find candidates, then query_database to check their
grades) within what looks like one turn to the user.

Multi-turn conversation is just "the caller keeps passing back a growing
`messages` list" -- there's no separate memory system to build.
"""

import json

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_TOKENS
from agent.system_prompt import SYSTEM_PROMPT
from tools.schemas import ALL_TOOL_SCHEMAS
from tools.query_database import query_database
from tools.search_syllabi import search_syllabi

_TOOL_DISPATCH = {
    "query_database": lambda tool_input: query_database(tool_input["sql"]),
    "search_syllabi": lambda tool_input: search_syllabi(
        tool_input["query"], tool_input.get("top_k", 5)
    ),
}

_MAX_TOOL_ROUNDS = 5  # safety valve against a runaway tool-call loop


def _get_client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Set it as an environment variable "
            "before running the app."
        )
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _execute_tool_call(block) -> dict:
    """Run the tool a single tool_use block asked for. Returns the raw
    result dict -- callers are responsible for JSON-serializing it into a
    tool_result content block."""
    handler = _TOOL_DISPATCH.get(block.name)
    if handler is None:
        return {"error": f"Unknown tool requested: {block.name}"}
    try:
        return handler(block.input)
    except Exception as e:
        # A tool implementation should already catch its own errors and
        # return {"error": ...} -- this is a last-resort backstop so a bug
        # in a tool never crashes the whole conversation turn.
        return {"error": f"Tool execution failed unexpectedly: {e}"}


def run_turn(messages: list[dict], user_message: str) -> tuple[list[dict], str, list[str]]:
    """
    Run one full conversational turn, including any tool-call rounds Claude
    needs internally. `messages` is the growing multi-turn history -- pass
    back what this function returns as `messages` next time you call it.

    Returns (updated_messages, final_answer_text, tools_used) where
    tools_used is an ordered list of tool names actually called this turn --
    useful for the UI to show the router's decision transparently, which
    matters here since the whole point of this project is that the routing
    decision is visible and correct, not a black box.
    """
    client = _get_client()
    messages = messages + [{"role": "user", "content": user_message}]
    tools_used: list[str] = []

    for _ in range(_MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOL_SCHEMAS,
            messages=messages,
        )

        messages = messages + [{"role": "assistant", "content": response.content}]

        if response.stop_reason != "tool_use":
            final_text = "".join(
                block.text for block in response.content if block.type == "text"
            )
            return messages, final_text, tools_used

        tool_result_blocks = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            tools_used.append(block.name)
            result = _execute_tool_call(block)
            tool_result_blocks.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })

        messages = messages + [{"role": "user", "content": tool_result_blocks}]

    # Safety valve tripped -- too many tool-call rounds without a final answer.
    return messages, (
        "I wasn't able to reach a final answer after several tool calls -- "
        "something may be looping. Please try rephrasing your question."
    ), tools_used