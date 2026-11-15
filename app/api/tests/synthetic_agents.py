"""Deliberately fictional browser transport; never constructs a paid provider."""

from yggdress_app.agent_models import ModelReply


class SyntheticLia:
    def ask(self, *_args, **_kwargs):
        return "A synthetic Lia response for browser verification."


class SyntheticModel:
    def complete(self, system, messages, tools):
        last = messages[-1]["content"]
        if isinstance(last, list):
            return ModelReply(
                [{"type": "text", "text": "A synthetic proposal is ready for your review."}]
            )
        names = {tool["name"] for tool in tools}
        if "tasks" in names:
            name, values = "tasks", {"request": "Create the synthetic task due 2 January 2030."}
        elif "propose_change" in names:
            name, values = (
                "propose_change",
                {
                    "operation": "task.create",
                    "data": {
                        "title": "Synthetic agent task",
                        "objective": "Keep the original synthetic goal.",
                        "due_date": "2030-01-02",
                    },
                    "explanation": "Requested in the synthetic browser conversation.",
                },
            )
        else:
            return ModelReply([{"type": "text", "text": "A synthetic read-only answer."}])
        return ModelReply(
            [{"type": "tool_use", "id": "synthetic-browser-tool", "name": name, "input": values}]
        )
