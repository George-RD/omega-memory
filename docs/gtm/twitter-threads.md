# X/Twitter Threads — Tuesday Launch

> Review before posting. Tag @mem0ai, @gaborcselle (Zep), @supermemoryai.

---

## Thread 1: MemoryStress Announcement

**Tweet 1 (hook):**
Every AI memory benchmark tests ~40 sessions.

We tested 1,000.

Here's what breaks. 🧵

**Tweet 2:**
We built MemoryStress — the first longitudinal benchmark for AI memory systems.

583 facts. 1,000 sessions. 10 simulated months. 300 questions.

Not "can you remember yesterday?" but "can you remember something from 6 months ago when 582 other facts have been stored since?"

**Tweet 3 (the curve):**
The key finding isn't the score — it's the shape of the degradation curve.

OMEGA peaks at session ~300 (42.4%) then degrades gradually to 32.7%.

Compression-based architectures? They cliff. Once the context window fills, old facts don't get harder to find — they're gone.

**Tweet 4 (the types):**
Seven question types expose different failure modes:

Temporal ordering: 41.2% ✓
Fact recall: 37.5% ✓
Contradiction resolution: 21.4% ✗

Contradiction resolution is the open problem. The LLM retrieves both versions of a fact and sometimes picks the wrong one.

**Tweet 5 (the cost):**
Full benchmark cost: $4.06

That's 4 cents per correct answer. GPT-4o for generation, answering, and grading. 41 minutes total.

We publish the cost because nobody else does.

**Tweet 6 (context):**
For context: OMEGA scores 95.4% on LongMemEval (#1 on the leaderboard).

MemoryStress is 25x the session volume with adversarial conditions. The absolute number will go up. The benchmark is calibrated to reveal real architectural differences.

**Tweet 7 (CTA):**
MemoryStress is open source. Run it on your system:

Dataset: huggingface.co/datasets/singularityjason/memorystress
GitHub: github.com/omega-memory/omega-memory
Full results: omegamax.co/blog/why-we-built-memorystress

@mem0ai @gaborcselle @supermemoryai — we'd love to see your scores.

---

## Thread 2: Comparison Data

**Tweet 1 (hook):**
We compared AI memory systems across two benchmarks.

One tests 40 sessions. The other tests 1,000.

The results tell very different stories.

**Tweet 2:**
LongMemEval (the standard, ICLR 2025):

OMEGA: 95.4% — #1
Mastra: 94.87% ($13M funded)
Zep/Graphiti: 71.2%
Mem0: not published

40 clean sessions. Good test of retrieval quality. Tells you nothing about scale.

**Tweet 3:**
MemoryStress (ours, 2026):

1,000 sessions. 583 facts. 10 months simulated.

OMEGA: 32.7% (98/300)
Everyone else: untested

The gap between 95.4% and 32.7% on the same system tells you exactly how much harder the long-horizon problem is.

**Tweet 4:**
Three architectures, three bets:

Mem0: managed cloud (47K stars, $0 to start)
Zep: temporal knowledge graph (23K stars, Neo4j required)
OMEGA: local SQLite, zero dependencies (5 stars, pip install)

Different constraints → different winners.

**Tweet 5:**
Honest take:

Mem0 wins if you want managed cloud.
Zep wins if you need deep graph queries.
OMEGA wins if you want local-first + best benchmarks.

None wins everywhere. Pick the constraint that matches yours.

Full comparison: omegamax.co/blog/omega-vs-mem0-vs-zep

**Tweet 6 (CTA):**
OMEGA is open source, local-first, Apache 2.0.

30-second install:
pip install omega-memory && omega setup

No API keys. No Docker. No cloud. Just memory that works.

github.com/omega-memory/omega-memory
