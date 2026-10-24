# Evals

The eval set: 20 to 30 questions with known answers, spread across direct lookup, multi-hop, page-precise, negative and temporal cases. Run it after every change to the node format, the gateway skill or any agent. A failing eval blocks the next phase.

The questions and answers are about the private brain, so `questions.yaml` lives in the brain repo (D30). This folder documents the question format and holds `fixture-brain/`: a synthetic brain with invented people, organisation and dates, used to test the format, the runner and the validator without touching real data. The runner lives in `app/` and reads a brain path at runtime. Nothing here is personal data (D4).
