# Show HN Post — Tuesday Feb 18, 8-10am PT

## Title

Show HN: OMEGA – Persistent memory for AI coding agents (local, SQLite, MCP)

## URL

https://github.com/omega-memory/omega-memory

## Text

Most agents are smart but amnesic. Every session starts from zero.

I'm a founder, not a developer. I've spent 25 years building AI companies. Last year I started using Claude Code to build everything: websites, APIs, data pipelines, automation. It worked, but I was re-explaining my stack, my preferences, and last week's decisions every single session.

So I built OMEGA: a minimal MCP server that persists decisions, error patterns, and lessons across sessions. Single SQLite file, runs locally, no API keys. `pip install omega-memory`. Apache-2.0, works with any MCP-compatible client.

After months of daily use I've accumulated 700+ memories. The impact is transformative. New sessions auto-load context: my five active projects, that we chose Supabase over Prisma last month, that the LinkedIn API rate-limits at 100 posts/day, that I'm in Bangkok so timestamps need +7h. No manual prompting. It resumes exactly where the last session left off. As a founder, this is what made AI coding agents actually usable for me. Not model upgrades, not bigger context windows. Memory.

OMEGA scores 95.4% on LongMemEval (ICLR 2025), #1 on the leaderboard, ahead of Mem0 ($23.7M raised) and Mastra ($13M). One person, zero funding, fully open-source. Scores are model-dependent (84% with GPT-4o, 95% with GPT-4.1). Benchmark script is in the repo for verification.

Beyond recall, accumulated memories enable behavioral analysis: tracking which decisions get revisited, which errors recur, which architectural choices survive. v1 already flags patterns like "Supabase connection error hit 12 times across 6 sessions." The longer-term goal is proactive context loading before you even ask.

I also built MemoryStress (https://github.com/omega-memory/memorystress), a longitudinal benchmark: 583 facts, 1000 sessions, 300 questions simulating 10 months of real usage. It tests what existing evals miss: contradictions, temporal reasoning, facts that evolve over time. Published on GitHub and HuggingFace.

Building this shifted how I think about AI. We're not waiting for AGI as some distant event. When an agent builds compounding, personal memory of your work, your decisions, your patterns, it crosses a threshold into something that feels like continuous intelligence. For the people using these tools daily, that threshold is now.

Feedback welcome. Docs and architecture: https://omegamax.co
