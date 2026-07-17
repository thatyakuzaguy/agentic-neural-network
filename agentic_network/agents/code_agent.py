from agentic_network.agents.base_agent import BaseAgent, load_prompt
from agentic_network.models.base import BaseModelClient


class CodeAgent(BaseAgent):
    def __init__(self, model: BaseModelClient) -> None:
        super().__init__("Code Agent", model, load_prompt("code"))

