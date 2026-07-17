# ANN Pipeline Routing

The Pipeline Router is deterministic. Qwen3-4B may propose intent, but routing must resolve to known ANN routes.

## Current Route Map

| Intent | Existing ANN stages |
| --- | --- |
| `requirement_analysis` | `product` |
| `architecture_design` | `product`, `architect`, `reviewer` |
| `implement_feature` | `product`, `architect`, `code`, `test`, `security`, `reviewer`, `final` |
| `debug_and_fix` | `product`, `code`, `test`, `fixer`, `reviewer` |
| `repository_analysis` | `product`, `architect`, `reviewer` |
| `security_review` | `security`, `reviewer`, `final` |
| `test_and_validate` | `test`, `reviewer`, `merge_readiness` |
| `autonomous_engineering` | `autonomous_loop` |
| `self_healing` | `self_healing` |
| `consensus_review` | `reviewer`, `final` |
| `patch_application` | `patch_quality`, `human_approval`, `patch_apply`, `test_runner` |
| `runtime_setup_or_diagnostics` | `product`, `reviewer` |
| `model_management` | `product`, `reviewer` |

Unknown pipelines are blocked instead of invented.

Patch application requests are held for approval in Desktop Chat.
