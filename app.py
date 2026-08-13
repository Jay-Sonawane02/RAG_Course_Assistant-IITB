"""
Streamlit UI. Still thin by design -- all real logic lives in agent/loop.py
and tools/. The one meaningful addition here is displaying which tool(s)
Claude actually called per answer, since that's the visible proof the
router is making a real decision each turn, not just a hidden detail.
"""

import streamlit as st

from agent.loop import run_turn

st.set_page_config(page_title="IITB CSE Course Assistant", page_icon="📚", layout="wide")

# Small CSS pass: tool-usage badges and a bit more breathing room. Kept
# minimal on purpose -- Streamlit's own chat components already look
# reasonable, this just adds the one custom element (badges) they don't
# have a built-in for.
st.markdown("""
<style>
.tool-badge {
    display: inline-block;
    padding: 2px 10px;
    margin: 2px 4px 2px 0;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
}
.tool-badge-sql { background-color: #2b4a3e; color: #7fd9a8; }
.tool-badge-vector { background-color: #3a2b4a; color: #c9a8d9; }
.tool-badge-none { background-color: #333; color: #999; }
</style>
""", unsafe_allow_html=True)

_BADGE_LABELS = {
    "query_database": ('<span class="tool-badge tool-badge-sql">🗄️ SQL query</span>'),
    "search_syllabi": ('<span class="tool-badge tool-badge-vector">🔍 Vector search</span>'),
}

_EXAMPLE_QUESTIONS = [
    "Which ML electives are easy to score well in?",
    "What are the prerequisites for CS725?",
    "Are there any courses that cover reinforcement learning?",
    "What are some good PG-level electives in security?",
]


def render_tool_badges(tools_used: list[str]) -> str:
    if not tools_used:
        return '<span class="tool-badge tool-badge-none">💬 Direct answer, no tools used</span>'
    seen = []
    for t in tools_used:
        if t not in seen:
            seen.append(t)
    return "".join(_BADGE_LABELS.get(t, t) for t in seen)


with st.sidebar:
    st.header("📚 About")
    st.markdown(
        "Answers questions about IITB CSE electives by routing each query "
        "to the right tool automatically:\n\n"
        "- **🗄️ SQL** for grades, prerequisites, credits, instructors\n"
        "- **🔍 Vector search** for topic/content questions\n\n"
        "Both tools get used together when a question needs it — e.g. "
        "*'easy ML electives'* needs semantic search to find candidates, "
        "then SQL to check their grades."
    )

    st.divider()
    st.subheader("Try asking")
    for question in _EXAMPLE_QUESTIONS:
        if st.button(question, use_container_width=True, key=f"example_{question}"):
            st.session_state.pending_question = question

    st.divider()
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.display_history = []
        st.rerun()

st.title("📚 IITB CSE Course Assistant")
st.caption(
    "Ask about electives, prerequisites, grade history, or course content. "
    "Multi-turn — feel free to ask follow-up questions."
)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "display_history" not in st.session_state:
    st.session_state.display_history = []  # list of (role, text, tools_used)

for entry in st.session_state.display_history:
    role, text = entry[0], entry[1]
    with st.chat_message(role):
        st.markdown(text)
        if role == "assistant" and len(entry) > 2:
            st.markdown(render_tool_badges(entry[2]), unsafe_allow_html=True)

pending = st.session_state.pop("pending_question", None)
user_input = st.chat_input("Ask about a course, e.g. 'which ML electives are easy to score well in?'")
user_input = user_input or pending

if user_input:
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                updated_messages, answer, tools_used = run_turn(st.session_state.messages, user_input)
                st.session_state.messages = updated_messages
            except RuntimeError as e:
                answer, tools_used = f"⚠️ {e}", []
            except Exception as e:
                answer, tools_used = f"⚠️ Something went wrong: {e}", []
        st.markdown(answer)
        st.markdown(render_tool_badges(tools_used), unsafe_allow_html=True)

    st.session_state.display_history.append(("user", user_input))
    st.session_state.display_history.append(("assistant", answer, tools_used))