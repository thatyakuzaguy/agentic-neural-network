from agentic_network.agents.base_agent import BaseAgent, load_prompt
from agentic_network.models.base import BaseModelClient
from agentic_network.models.deepseek_gguf import clean_deepseek_output
from agentic_network.models.qwen3 import clean_qwen3_product_output


class ProductAgent(BaseAgent):
    def __init__(self, model: BaseModelClient) -> None:
        output_cleaner = (
            clean_qwen3_product_output
            if getattr(model, "backend_name", "") == "qwen3"
            else clean_deepseek_output
        )
        super().__init__(
            "Product / Requirements Agent",
            model,
            load_prompt("product"),
            output_cleaner,
        )

    def run(self, input_text: str) -> str:
        product_runner = getattr(self.model, "run_product_instruction", None)
        if callable(product_runner):
            print(f"Starting {self.name}...")
            output = product_runner(input_text)
            print(f"Finished {self.name}.")
            return str(output).strip()
        return super().run(input_text)
