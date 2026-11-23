---
name: chain
description: A multi-hop question, where the answer to one step names the thing to look up next.
done_when:
  - I wrote down each hop and which note answered it.
  - Every hop has a cited fact, including the middle ones.
  - The final answer is about the last thing in the chain, not an earlier one.
  - If a hop broke, I said which one and what is missing.
---

# Chain

1. Break the question into hops: "the X of Y" → find Y, then its X.
2. Answer the first hop from its note, then follow the thread: the `[[slug]]` inside that fact, or the note's link line, to the next note. Open the next notes together when you can see them coming.
3. Cite every hop, not only the last one: the reader needs each step.
4. If a hop doesn't resolve, stop there. Say which hop is missing, and give what the earlier hops found.
