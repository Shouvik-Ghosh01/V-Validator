from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain.tools import tool

from backend.config import (
    LLM_MODEL,
    OPENAI_API_KEY,
    OPENAI_API_BASE,
)
from backend.agent.prompts import SYSTEM_PROMPT
from backend.rag.retriever import retrieve_chunks
from backend.utils.citation import extract_sources
from backend.safety.output_filter import is_safe_output


llm = ChatOpenAI(
    model=LLM_MODEL,
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_API_BASE,
    temperature=0.5,
)


# -------------------------------------------------
# RETRIEVER TOOL
# -------------------------------------------------
@tool
def internal_knowledge_retriever(query: str) -> str:
    """
    Retrieve relevant internal company documents.
    Returns formatted context or 'NO_CONTEXT'.
    """

    results = retrieve_chunks(query)

    if not results:
        return "NO_CONTEXT"

    context_parts = []
    for r in results:
        context_parts.append(
            f"""Source: {r['source']} (Page {r.get('page', 'N/A')})
Content:
{r['text']}"""
        )

    return "\n\n".join(context_parts)


# -------------------------------------------------
# AGENT INITIALIZATION
# -------------------------------------------------
agent = create_agent(
    model=llm,
    tools=[internal_knowledge_retriever],
    system_prompt=SYSTEM_PROMPT
)


# -------------------------------------------------
# MAIN AGENT EXECUTION
# -------------------------------------------------
def run_agent(query: str) -> dict:
    """
    Executes the agentic RAG pipeline and returns a grounded response.
    """
    result = agent.invoke({
        "messages": [
            {"role": "user", "content": query}
        ]
    })

    
    final_message = result["messages"][-1].content or ""

    if "NO_CONTEXT" in final_message:
        return {
            "answer": final_message,
            "sources": [],
        }

    if not is_safe_output(final_message):
        return {
            "answer": "Unable to provide a safe answer based on the available information.",
            "sources": [],
        }

    return {
        "answer": final_message,
        "sources": extract_sources(),
    }