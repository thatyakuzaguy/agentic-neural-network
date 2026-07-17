# ANN Intent Contract

`ANNIntentContract` is the versioned handoff between natural language and ANN pipelines.

## Version

`ann_intent_contract_v1`

## Required Fields

- `request_id`
- `conversation_id`
- `language`
- `primary_intent`
- `user_goal`
- `deliverables`
- `explicit_constraints`
- `forbidden_actions`
- `acceptance_criteria`
- `project_context`
- `recommended_pipeline`
- `recommended_agents`
- `risk_level`
- `requires_confirmation`
- `requires_human_approval`
- `missing_information`
- `ambiguities`
- `conflicts`
- `confidence`
- `status`

Every requirement, constraint, prohibition, ambiguity, conflict, and acceptance criterion keeps:

- `source_message_id`
- `source_excerpt`
- `confidence`
- `classification`
- `priority`

## Statuses

- `draft`
- `needs_clarification`
- `validated`
- `rejected`
- `ready_for_execution`

## Validation

Validation checks schema, traceability, risk values, status values, C: path blocking, coverage of restriction markers, and excessive list sizes.

## Artifacts

The Desktop Chat runtime writes:

- `88_intent_contract.json`
- `89_context_bundle.json`
- `90_pipeline_route.json`
- `91_prompt_compilation.json`
- `92_model_lifecycle.json`
- `93_conversation_orchestrator_events.json`
- `94_conversation_orchestrator_summary.md`
