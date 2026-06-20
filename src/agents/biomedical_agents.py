"""
biomedical_agents.py
Four-agent biomedical research pipeline (Triage -> Clarifying -> Instruction
-> Research) built on the OpenAI Agents SDK and Deep Research API.

The Research Agent is given both the hosted WebSearchTool and a local
GraphRAG tool (`search_sr_corpus`) so it can synthesise web evidence with
findings already curated in the project's systematic-review corpus.

Refactored from notebooks/biomedical_research_agents.ipynb so the same
pipeline can be invoked from scripts, the notebook, or other agents.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel
from openai import AsyncOpenAI
from agents import Agent, Runner, WebSearchTool, RunConfig, set_default_openai_client

from src.agents.graphrag_tool import search_sr_corpus

load_dotenv()

client = AsyncOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    timeout=600.0,
)
set_default_openai_client(client)
os.environ.setdefault("OPENAI_AGENTS_DISABLE_TRACING", "1")


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------
TRIAGE_AGENT_PROMPT = """
You are a biomedical research triage specialist. Evaluate the user's research query and decide whether
additional clarification is needed before deep research can be conducted.

Route to the Clarifying Questions Agent if ANY of the following are true:
- The patient population, disease, or condition is not clearly specified
- The intervention, drug, or therapy of interest is ambiguous
- The desired outcome measure or endpoint is unclear
- The query is too broad to yield a focused research report
- The time horizon or study design preference is absent and would materially affect results

Route directly to the Research Instruction Agent if:
- The query is specific and contains sufficient PICO elements (Population, Intervention, Comparator, Outcome)
- The research scope is well-defined and actionable

Return EXACTLY ONE function call:
- transfer_to_clarifying_questions_agent  if clarification is needed
- transfer_to_research_instruction_agent  if the query is ready for research
"""

CLARIFYING_AGENT_PROMPT = """
You are a biomedical research clarification specialist. Your goal is to gather precisely the information
needed to conduct focused, high-quality clinical or scientific research.

Ask 2-3 targeted clarifying questions using the PICO framework as a guide:
  P  Population / Patient / Problem
  I  Intervention / Exposure / Test
  C  Comparator / Control (if relevant)
  O  Outcome / Endpoint of interest

GUIDELINES:
1. Be specific and clinically grounded. Ask about patient demographics, disease stage, line of therapy,
   biomarkers, or regulatory context where relevant.
2. Do not ask for information already provided. Only ask about missing dimensions.
3. Be concise and professional. Use numbered questions.
4. Tailor to context. For drug research ask about mechanism class or indication. For genomics ask about
   variant type or cancer type. For clinical trials ask about phase or endpoint type.
"""

RESEARCH_INSTRUCTION_AGENT_PROMPT = """
You are a biomedical research instruction architect. Take the user's query (and any clarification answers)
and rewrite it into a detailed, structured research brief for a Deep Research model.

OUTPUT ONLY THE RESEARCH INSTRUCTIONS. Then transfer to the research agent.

GUIDELINES:
1. Maximize specificity. Include all known PICO elements, patient population, disease stage, biomarkers.
2. Fill unstated dimensions as open-ended (e.g. "Comparator: any / no specific constraint").
3. Avoid unwarranted assumptions.
4. Request structured output:
   - Executive Summary
   - Background & Disease Context
   - Evidence Review (organised by study type: RCTs, observational, meta-analyses)
   - Key Data Tables
   - Clinical Implications
   - Limitations & Evidence Gaps
   - References (inline URL citations)
5. Prioritise high-quality sources: PubMed/MEDLINE, ClinicalTrials.gov, FDA/EMA labels, peer-reviewed journals.
6. Tell the model to query the local SR corpus first via the search_sr_corpus tool, then expand to the web.
7. Evidence hierarchy: RCT > prospective cohort > retrospective > case series > expert opinion.
"""


class Clarifications(BaseModel):
    questions: List[str]


# --------------------------------------------------------------------------
# Agents
# --------------------------------------------------------------------------
RESEARCH_MODEL = os.environ.get("RESEARCH_MODEL", "o4-mini-deep-research-2025-06-26")
SUPPORT_MODEL = os.environ.get("SUPPORT_MODEL", "gpt-4o-mini")


def build_agents() -> tuple[Agent, Agent, Agent, Agent]:
    research_agent = Agent(
        name="Biomedical Research Agent",
        model=RESEARCH_MODEL,
        instructions=(
            "You are a senior biomedical research scientist. Use the local "
            "GraphRAG SR corpus first via the search_sr_corpus tool, then "
            "supplement with web search. Prioritise peer-reviewed literature, "
            "clinical trial registries, and regulatory sources. Cite all "
            "sources inline."
        ),
        tools=[search_sr_corpus, WebSearchTool()],
    )
    instruction_agent = Agent(
        name="Research Instruction Agent",
        model=SUPPORT_MODEL,
        instructions=RESEARCH_INSTRUCTION_AGENT_PROMPT,
        handoffs=[research_agent],
    )
    clarifying_agent = Agent(
        name="Clarifying Questions Agent",
        model=SUPPORT_MODEL,
        instructions=CLARIFYING_AGENT_PROMPT,
        output_type=Clarifications,
        handoffs=[instruction_agent],
    )
    triage_agent = Agent(
        name="Triage Agent",
        model=SUPPORT_MODEL,
        instructions=TRIAGE_AGENT_PROMPT,
        handoffs=[clarifying_agent, instruction_agent],
    )
    return triage_agent, clarifying_agent, instruction_agent, research_agent


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------
async def run_research(
    query: str,
    mock_answers: Optional[Dict[str, str]] = None,
    verbose: bool = False,
):
    triage_agent, _, _, _ = build_agents()
    print(f"\n{'='*60}\nQUERY: {query}\n{'='*60}")

    stream = Runner.run_streamed(
        triage_agent, query, run_config=RunConfig(tracing_disabled=True)
    )

    async for ev in stream.stream_events():
        if ev.type == "agent_updated_stream_event":
            print(f"\n--- Agent: {ev.new_agent.name} ---")
        elif isinstance(getattr(ev, "item", None), Clarifications):
            print("\n[Clarifying Agent] Questions:")
            reply_parts = []
            for q in ev.item.questions:
                ans = (mock_answers or {}).get(q, "No preference.")
                print(f"  Q: {q}\n  A: {ans}")
                reply_parts.append(f"**{q}**\n{ans}")
            stream.send_user_message("\n\n".join(reply_parts))
            continue
        elif (
            ev.type == "raw_response_event"
            and hasattr(ev.data, "item")
            and hasattr(ev.data.item, "action")
        ):
            action = ev.data.item.action or {}
            if action.get("type") == "search":
                print(f"  [Web Search] {action.get('query')!r}")
        elif verbose:
            print(ev)

    print("\n[Research complete]")

    # Best-effort durable run record. No-op without AZURE_DOCDB_CONNECTION_STRING;
    # persistence must never fail a research run.
    try:
        from datetime import datetime, timezone
        from src.store import docdb

        if docdb.enabled():
            final_output = getattr(stream, "final_output", None)
            rec_id = docdb.save_run_record(
                {
                    "app": "agentic_research_team",
                    "query": query,
                    "final_output": str(final_output) if final_output is not None else None,
                    "created_at": datetime.now(timezone.utc),
                }
            )
            if rec_id:
                print(f"[docdb] run record saved: {rec_id}")
    except Exception as exc:  # noqa: BLE001 - never break a run on persistence
        print(f"[docdb] run record not saved: {exc}")

    return stream
