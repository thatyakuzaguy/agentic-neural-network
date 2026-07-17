from agentic_network.agents.base_agent import BaseAgent, load_prompt
from agentic_network.models.base import BaseModelClient


class TestEngineerAgent(BaseAgent):
    def __init__(self, model: BaseModelClient) -> None:
        super().__init__("Test Engineer Agent", model, load_prompt("test_engineer"))

