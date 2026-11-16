"""Read-only subprocess boundary to the existing Lia, using her own environment."""

import json
import os
import subprocess
from pathlib import Path

from .agent_models import AgentError


class ExistingLia:
    def __init__(self, project, skills=None, brain_root=None):
        self.project = Path(project).resolve()
        relative = ".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python"
        self.python = self.project / "app" / relative
        if not self.python.is_file():
            self.python = self.project / relative
        self.script = Path(__file__).resolve().parents[2] / "scripts/lia_application_bridge.py"
        self.skills = skills
        self.brain_root = brain_root

    def _call(self, value=None):
        command = [str(self.python), str(self.script), "--brain-project", str(self.project)]
        if self.skills:
            command.extend(["--skills", str(self.skills)])
        if value is None:
            command.append("--inspect")
        try:
            result = subprocess.run(
                command,
                input=json.dumps(value, ensure_ascii=False).encode() if value else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=150 if value else 15,
                check=False,
                cwd=self.project,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                env={
                    **os.environ,
                    **({"YGGDRAS_BRAIN": str(self.brain_root)} if self.brain_root else {}),
                },
            )
            if result.returncode or len(result.stdout) > 240000:
                raise AgentError(
                    "The existing Lia service is unavailable. No Brain changes were made."
                )
            return json.loads(result.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            raise AgentError(
                "The Lia connection was interrupted. It was not automatically retried."
            ) from None

    def inspect(self):
        return self._call()

    def ask(self, question, context="", model="default"):
        result = self._call({"question": question, "context": context, "model": model})
        answer = result.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise AgentError("Lia returned no answer.")
        return answer[:20000]
