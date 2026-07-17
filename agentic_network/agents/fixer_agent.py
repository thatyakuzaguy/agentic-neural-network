from agentic_network.agents.base_agent import BaseAgent, load_prompt
from agentic_network.models.base import BaseModelClient


class FixerAgent(BaseAgent):
    def __init__(self, model: BaseModelClient) -> None:
        super().__init__("Fixer Agent", model, load_prompt("fixer"))

