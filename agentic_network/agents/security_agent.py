from agentic_network.agents.base_agent import BaseAgent, load_prompt
from agentic_network.models.base import BaseModelClient
from agentic_network.models.deepseek_gguf import clean_deepseek_output


class SecurityAgent(BaseAgent):
    def __init__(self, model: BaseModelClient) -> None:
        super().__init__("Security Agent", model, load_prompt("security"), clean_deepseek_output)
