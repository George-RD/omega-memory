---
title: "Sessions Aren't Memory: Adding Persistent Knowledge to Claude Agent SDK"
published: false
description: "The Claude Agent SDK can resume sessions, but replaying a transcript isn't the same as having searchable, structured knowledge. Here's how to fix that."
tags: ai, python, opensource, claude
---

The Claude Agent SDK ships with session persistence. You can call `resume=session_id` and pick up a conversation where you left off. That's useful. It's also not memory.

Here's the difference. When you resume a session, the SDK replays the entire conversation transcript back to Claude's API. All of it. If your session ran 50 turns, you're paying for those 50 turns of input tokens again. And Claude has to re-read the whole thing to figure out what matters.

That's like re-reading your entire diary every morning to remember where you put your keys.

What you actually want is structured knowledge that persists between runs. Not "what did we talk about last time?" but "what do you know about this project's auth system?"

## What Sessions Give You

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

options = ClaudeAgentOptions(model="claude-sonnet-4-5-20250514")

# First run
async with ClaudeSDKClient(options=options) as client:
    response = await client.query("Set up JWT auth for the API")
    session_id = client.session_id  # save this

# Second run - replays entire conversation
async with ClaudeSDKClient(options=options) as client:
    response = await client.query(
        "What auth approach did we decide on?",
        resume=session_id
    )
```

This works. But you're paying full input token cost for that entire first session. And if you had 10 sessions over the past month, you can only resume one of them. The other 9 are gone.

## What Memory Gives You

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

options = ClaudeAgentOptions(
    model="claude-sonnet-4-5-20250514",
    mcp_servers={
        "omega": {
            "command": "python3",
            "args": ["-m", "omega.server.mcp_server"]
        }
    }
)

# Any session, any time - agent queries what it needs
async with ClaudeSDKClient(options=options) as client:
    response = await client.query(
        "What auth approach did we decide on for this project?"
    )
    # OMEGA surfaces the JWT decision from 3 weeks ago
    # Cost: one semantic search, not a full transcript replay
```

The agent asks for what it needs, when it needs it. It doesn't replay old conversations. It queries structured memories with semantic search and gets back the relevant ones.

## The Setup (Two Options)

### Option A: External MCP Server (3 lines)

The simplest path. OMEGA runs as a separate process, same as it does with Claude Code.

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

options = ClaudeAgentOptions(
    model="claude-sonnet-4-5-20250514",
    mcp_servers={
        "omega": {
            "command": "python3",
            "args": ["-m", "omega.server.mcp_server"]
        }
    }
)

async with ClaudeSDKClient(options=options) as client:
    # Agent now has access to omega_store, omega_query,
    # omega_checkpoint, omega_resume_task, and 8 more tools
    response = await client.query("What do you know about this project?")
```

That's it. The agent gets 12 memory tools. It can store decisions, query past context, checkpoint tasks, and resume them later. OMEGA handles semantic search, deduplication, contradiction detection, and memory decay.

### Option B: In-Process Tools (No Subprocess)

If you don't want a separate process, wrap OMEGA's Python API as in-process SDK tools. No IPC overhead.

```python
from claude_agent_sdk import tool, create_sdk_mcp_server, ClaudeAgentOptions
from omega import store, query

@tool(
    "omega_store",
    "Store a memory (decision, lesson, preference, or error)",
    {"content": str, "event_type": str}
)
async def omega_store(args):
    result = store(args["content"], args.get("event_type", "memory"))
    return {"content": [{"type": "text", "text": result}]}

@tool(
    "omega_query",
    "Search memories by semantic similarity",
    {"query_text": str, "limit": int}
)
async def omega_query(args):
    result = query(args["query_text"], limit=args.get("limit", 5))
    return {"content": [{"type": "text", "text": result}]}

memory = create_sdk_mcp_server(
    name="omega",
    version="1.0.0",
    tools=[omega_store, omega_query]
)

options = ClaudeAgentOptions(
    model="claude-sonnet-4-5-20250514",
    mcp_servers={"omega": memory},
    allowed_tools=["mcp__omega__omega_store", "mcp__omega__omega_query"]
)
```

This gives you the two most-used tools (store and query) without spawning a subprocess. You can add more tools from OMEGA's API (`checkpoint`, `resume_task`, `welcome`, `remind`, etc.) the same way.

## What This Looks Like in Practice

Build an agent that learns across runs:

```python
import asyncio
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

async def run_agent(task: str):
    options = ClaudeAgentOptions(
        model="claude-sonnet-4-5-20250514",
        mcp_servers={
            "omega": {
                "command": "python3",
                "args": ["-m", "omega.server.mcp_server"]
            }
        }
    )

    async with ClaudeSDKClient(options=options) as client:
        # Agent automatically queries OMEGA for relevant context
        # and stores new decisions/lessons as it works
        async for message in client.query(task):
            if hasattr(message, 'content'):
                print(message.content)

# Monday: agent makes architectural decisions
asyncio.run(run_agent("Set up the API. Use FastAPI with JWT auth."))

# Wednesday: agent remembers Monday's decisions
asyncio.run(run_agent("Add rate limiting to the API"))
# OMEGA surfaces: "JWT auth chosen for stateless horizontal scaling"

# Friday: agent recalls the full context
asyncio.run(run_agent("Write integration tests for the auth middleware"))
# OMEGA surfaces: JWT decision + rate limiting approach
```

No session IDs to track. No transcripts to replay. The agent builds up project knowledge over time and retrieves what's relevant.

## Sessions vs Memory: When to Use Which

Sessions and memory solve different problems. Use both.

**Use sessions** when you're in the middle of a multi-turn task and need to pause/resume the exact conversation state. Sessions are cheap for short conversations and preserve the full conversational flow.

**Use memory** when knowledge should outlive the conversation. Architectural decisions, debugging lessons, code style preferences, project context. Things that matter in session 47, not just session 2.

The sweet spot: use OMEGA for persistent knowledge and sessions for within-task continuity. Your agent starts each run by pulling relevant memories (costs a few hundred tokens) instead of replaying old transcripts (costs thousands).

## Install

```bash
pip install omega-memory[server] claude-agent-sdk
omega setup
```

{% github omega-memory/omega-memory %}

OMEGA is Apache-2.0. 12 MCP tools, SQLite storage, local ONNX embeddings. No cloud, no API keys for the memory system itself. It scores 95.4% on LongMemEval (ICLR 2025), #1 on the leaderboard.

The Agent SDK integration is the same OMEGA that works with Claude Code, Cursor, and Windsurf. If you're already running OMEGA with Claude Code, your Agent SDK agents get the same memory database. Everything compounds.
