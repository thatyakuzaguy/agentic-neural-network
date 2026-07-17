from pathlib import Path


ROOT = Path(r"D:\AgenticEngineeringNetwork")


def test_api_images_include_git_for_repair_diff_validation() -> None:
    dockerfile = (ROOT / "docker" / "api.Dockerfile").read_text(encoding="utf-8")
    gpu_dockerfile = (ROOT / "docker" / "api.gpu.Dockerfile").read_text(encoding="utf-8")

    assert " git " in dockerfile or " git \\" in dockerfile
    assert " git " in gpu_dockerfile or " git \\" in gpu_dockerfile
