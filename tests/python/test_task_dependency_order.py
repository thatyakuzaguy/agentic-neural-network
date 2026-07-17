from agentic_engineering_network.orchestration.tasks import decompose_idea


def test_full_stack_task_graph_orders_backend_before_frontend() -> None:
    tasks = decompose_idea("Build a FastAPI todo app with a React frontend")
    by_id = {task.task_id: task for task in tasks}
    order = {task.task_id: index for index, task in enumerate(tasks)}

    assert order["database_generation"] < order["backend_generation"] < order["frontend_generation"]
    assert by_id["backend_generation"].dependencies == ("database_generation",)
    assert by_id["frontend_generation"].dependencies == ("backend_generation",)


def test_quality_gates_depend_on_implementation_outputs() -> None:
    tasks = decompose_idea("Build a SaaS CRM")
    by_id = {task.task_id: task for task in tasks}

    assert set(by_id["qa_verification"].dependencies) == {
        "backend_generation",
        "frontend_generation",
        "devops_packaging",
    }
    assert set(by_id["security_review"].dependencies) == {
        "backend_generation",
        "database_generation",
    }
    assert by_id["release_package"].dependencies == ("meta_review",)
