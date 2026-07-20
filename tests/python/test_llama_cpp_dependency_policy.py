from scripts.security.verify_llama_cpp_dependency_policy import verify_policy


def test_llama_cpp_dependency_policy_is_fail_closed() -> None:
    result = verify_policy()

    assert result["status"] == "PASS"
    assert result["diskcache_in_dependency_contract"] is False
    assert result["llama_cpp_install_mode"] == "no-deps"
    assert result["persistent_disk_cache"] == "disabled"
