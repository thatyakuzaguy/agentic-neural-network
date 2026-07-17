from agentic_engineering_network.agents.definitions import AgentName, get_agent_registry


def test_registry_contains_required_agents() -> None:
    names = {agent.name for agent in get_agent_registry()}

    assert len(names) == 15
    assert AgentName.PRODUCT_MANAGER in names
    assert AgentName.RELEASE in names
    assert AgentName.PRODUCT_REVIEW in names
    assert AgentName.META_REVIEW in names


def test_each_agent_has_operational_contract() -> None:
    for agent in get_agent_registry():
        assert agent.role
        assert agent.goals
        assert agent.tools
        assert agent.outputs
        assert agent.input_schema
        assert agent.output_schema
        assert agent.validation_logic
        assert agent.quality_rubric
        assert agent.failure_modes
        assert agent.retry_policy
        assert agent.escalation_rules
