# AI Copy Rules: Anti-Slop Writing Guide

**Status: Active**
**Last updated: Feb 15, 2026**
**Scope: All public-facing copy (website, social, docs, README, changelogs)**

These rules apply to any agent (Claude, GPT, Grok, or human using AI assistance) writing copy that ships to users. The goal: write like a human engineer, not a language model.

---

## 1. Punctuation

### BANNED: Em dashes
Never use em dashes (the long dash: `U+2014`). They are the single most reliable AI writing tell. Reddit data shows em dash usage tripled in tech/startup writing since 2023. Replace with:
- **Commas** for parenthetical asides
- **Periods** for separating independent thoughts
- **Colons** for introducing explanations
- **Parentheses** for brief clarifications

| Before (AI) | After (human) |
|---|---|
| Not just storage — search and forgetting | Not just storage, but search and forgetting |
| Zero cloud dependency — everything local | Zero cloud dependency. Everything runs locally. |
| 95.4% on LongMemEval — #1 worldwide | 95.4% on LongMemEval. #1 worldwide. |
| OMEGA vs Mem0 — An Honest Comparison | OMEGA vs Mem0: An Honest Comparison |

### BANNED: Semicolons joining independent clauses
AI uses semicolons to sound scholarly. Use a period instead.

### BANNED: Ellipsis for trailing off
"And then..." reads as filler. Cut the sentence or finish the thought.

### LIMIT: Exclamation marks
Maximum one per page. Prefer zero.

---

## 2. Words

### BANNED words (hard reject)

| Word | Why | Replace with |
|---|---|---|
| delve/delves | #1 AI tell worldwide, 25x overuse rate | explore, examine, look at |
| leverage | corporate buzzword | use |
| seamless/seamlessly | meaningless to developers | describe the actual integration |
| utilize | pretentious synonym for "use" | use |
| crucial | AI filler adjective | important, or cut the word |
| robust | vague, overused | describe what makes it reliable |
| cutting-edge | unverifiable superlative | cite the benchmark or spec |
| revolutionary | overclaim | state the fact |
| innovative | means nothing | describe the actual innovation |
| unprecedented | almost never true | name the precedent it beats |
| game-changer | hyperbolic | state the impact with numbers |
| supercharge | mocked in every dev community | describe the actual speedup |
| unlock | marketing speak | enable, or describe what happens |
| harness | AI-flavored "use" | use |
| streamline | vague optimization claim | describe what got faster/simpler |
| foster | AI-formal, rarely used by humans | build, encourage, create |
| showcasing | AI tell, stilted | showing |
| underscore | AI tell for "emphasize" | highlight, show |
| multifaceted | AI padding | complex, or just describe the facets |
| holistic | management-speak | comprehensive, or cut it |
| landscape | AI loves "the X landscape" | space, field, or cut it |
| tapestry | AI creative writing tell | (delete the metaphor) |
| paradigm | unless quoting Kuhn, never | approach, model, pattern |
| synergy | universally mocked | (rewrite the sentence) |
| empower | patronizing | enable, let, allow |
| elevate | AI-inflated "improve" | improve |

### BANNED phrases (hard reject)

| Phrase | Replace with |
|---|---|
| "In today's fast-paced world" | (delete, start with the point) |
| "As technology continues to evolve" | (delete, start with the point) |
| "At the end of the day" | (delete or "ultimately") |
| "It's worth noting that" | (delete, just state it) |
| "It's important to remember" | (delete, just state it) |
| "Let's dive in" / "Let's delve into" | (delete, start with content) |
| "In the realm of" | "in" |
| "At its core" | (delete or "fundamentally") |
| "Not just X, but Y" | rewrite without the contrast formula |
| "It's not X, it's Y" | rewrite (6.3x overuse vs human writing) |
| "X is a game-changer" | state what X does with numbers |
| "The bottom line" | (delete, just state it) |
| "Here's the thing" | (delete, just state the thing) |
| "Think about it" | (delete) |
| "Excited to announce" / "Thrilled to share" | "[Thing] is live" or "Shipping [thing]" |
| "Without further ado" | (delete) |
| "But here's the kicker" | (delete, just state it) |

---

## 3. Structure

### BANNED: The Rule of Three (reflexive triads)
AI defaults to three-item lists and three-beat cadences. Vary your counts.

| AI pattern | Human alternative |
|---|---|
| "Fast, efficient, and reliable" | "Retrieval takes ~50ms" (one specific claim) |
| "Think bigger. Act bolder. Move faster." | (delete this kind of sentence) |
| Three identical-length bullet points | Vary bullet length. Two is fine. Four is fine. |

### BANNED: Identical sentence lengths
AI writes every sentence at roughly the same length. Vary it. Short. Then longer when the thought requires it. Then short again.

### BANNED: Zoom-out conclusions
AI ends with vague "bigger picture" statements nobody asked for. End with the last concrete point.

| AI ending | Human ending |
|---|---|
| "As AI continues to evolve, memory systems will play an increasingly crucial role in shaping the future of development." | "Install with `pip install omega-memory`. Run `omega setup`." |

### BANNED: Warm-up sentences
Never start with "In the world of...", "When it comes to...", "If you've ever...". Start with the substance.

### BANNED: Gerund-comma openers
"Building memory systems, I've learned..." is an AI fingerprint. Rewrite: "I learned something building memory systems."

### LIMIT: Parallelism
Some parallel structure is fine. Three or more items with identical grammatical structure in a row is an AI tell. Break the pattern.

---

## 4. Tone

### Write like you're typing in Slack, not drafting an essay.
- Contractions: use them ("it's", "don't", "we're")
- Fragments: fine when they add rhythm ("No cloud required.")
- Starting with "And" or "But": fine
- Questions mid-paragraph: fine if genuine, not rhetorical filler

### No hedging
Remove: "arguably", "perhaps", "to be fair", "in many ways", "it remains to be seen", "only time will tell"

### No faux enthusiasm
Remove: "exciting", "incredible", "amazing", "huge" (unless the numbers back it up)

### No explaining what you're about to say
Bad: "In this section, we'll explore how OMEGA handles memory retrieval."
Good: "OMEGA retrieves memories in ~50ms using a five-stage pipeline."

---

## 5. Formatting

### BANNED: Emoji in professional copy
No emoji in website pages, docs, README, blog posts, or changelogs. Acceptable only in Discord community spaces and casual tweet replies.

### BANNED: Arbitrary bold for emphasis
Bold is for headings, labels, and UI element names. Not for making random words louder.

### BANNED: Unicode decorations
No fancy unicode arrows, multiplication signs, or styled text in copy.

### LIMIT: Bullet points
AI defaults to bullet lists for everything. Use prose when three or fewer items. Reserve bullets for genuine lists of 4+ items.

---

## 6. Self-Test

Before publishing any copy, check:

1. **Read it aloud.** Does it sound like a person talking, or a press release?
2. **Search for em dashes.** Replace every one.
3. **Count the triads.** If you have more than one three-item parallel structure per section, break one.
4. **Check the opener.** Does the first sentence deliver value, or warm up?
5. **Check the closer.** Does the last sentence give a concrete next step, or zoom out?
6. **Ctrl+F the banned words list.** Replace every hit.
7. **Vary sentence length.** If three consecutive sentences are similar length, rewrite one shorter or longer.

---

## Sources

- [Wikipedia: Signs of AI Writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
- [The Field Guide to AI Slop (Charlie Guo)](https://www.ignorance.ai/p/the-field-guide-to-ai-slop)
- [Slop Score (EQ-Bench)](https://eqbench.com/slop-score.html)
- [Red Flag Words (Blake Stockton)](https://www.blakestockton.com/red-flag-words/)
- [Grammarly: Common AI Words](https://www.grammarly.com/blog/ai/common-ai-words/)
- [Futurism: AI Overuses Specific Words](https://futurism.com/the-byte/ai-overuses-specific-words)
- [Antislop Framework (arXiv)](https://arxiv.org/pdf/2510.15061)
