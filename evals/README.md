# Evals

The eval set: 20 to 30 questions with known answers, spread across direct lookup, multi-hop, page-precise, negative and temporal cases. Run it after every change to the node format, the gateway skill or any agent. A failing eval blocks the next phase.

The questions and answers are about the private brain, so `questions.yaml` lives in the brain repo (D30). This folder holds only the runner and the question format, and reads the brain path at runtime. It never holds personal data (D4).
