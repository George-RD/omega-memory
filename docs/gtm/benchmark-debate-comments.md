# Benchmark Debate Comments — Draft

> Ready to post. Review before posting — these are externally visible.

---

## 1. Zep blog: "Lies, Damn Lies & Statistics"
**URL:** https://blog.getzep.com/lies-damn-lies-statistics-is-mem0-really-sota-in-agent-memory/

Great analysis of the benchmark validity issues. One dimension I haven't seen tested in either Zep's or Mem0's evaluations is longitudinal retention under accumulation pressure — what happens when a memory system runs for months and must handle 1,000+ sessions with contradictions, noise, and eviction decisions? We built MemoryStress to fill that gap: 583 facts across 1,000 GPT-4o-generated sessions spanning 10 simulated months, with 300 questions testing degradation curves across phases. The key finding is that persistent vector storage shows an inverted-U degradation curve (performance peaks at mid-scale as the embedding space enriches, then dips from noise) rather than collapsing like compression-only architectures. Dataset is open on HuggingFace at https://huggingface.co/datasets/singularityjason/memorystress if either team wants to test their systems under long-horizon conditions.

---

## 2. Cognee comparison: "AI Memory Tools Evaluation"
**URL:** https://www.cognee.ai/blog/deep-dives/ai-memory-tools-evaluation

Helpful comparison across the tools currently in the space. One system that wasn't included but has relevant benchmark data: OMEGA (local-first MCP memory server, https://github.com/omega-memory/omega-memory) scores 95.4% on LongMemEval and was recently tested on a new longitudinal benchmark called MemoryStress — 1,000 sessions, 583 facts, 300 questions across 10 simulated months to test degradation under accumulation pressure. The 32.7% score on MemoryStress (intentionally brutal, tests contradiction resolution and single-mention recall under noise) exposes a different dimension than snapshot-based evals: persistent vector storage maintains recall even at 1,000+ sessions, while compression-only approaches would hit token ceilings. Dataset is open at https://huggingface.co/datasets/singularityjason/memorystress — would be interesting to see how the tools in your comparison perform on it.

---

## 3. Mem0 GitHub: getzep/zep-papers issue #5
**URL:** https://github.com/getzep/zep-papers/issues/5

The methodology discussion here is spot-on — transparency and reproducibility matter. One gap across existing benchmarks (LongMemEval, MemoryAgentBench, BEAM) is that none test longitudinal retention under accumulation pressure: what happens at session 500? Session 1,000? When facts contradict over time? We built MemoryStress to address this: 583 facts embedded naturally in 1,000 GPT-4o conversations spanning 10 simulated months, with 300 questions testing degradation curves, contradiction resolution, and single-mention recall. The benchmark is intentionally brutal (OMEGA, our MCP memory server, scores 32.7%) but exposes architectural differences — persistent vector storage shows an inverted-U curve rather than monotonic decay. Full dataset and harness are open at https://huggingface.co/datasets/singularityjason/memorystress if either team wants to add it to their evaluation suite.
