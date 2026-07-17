# ANN Context Management

The Context Builder prevents dumping the entire conversation into a model.

## Context Layers

1. Conversation Buffer
2. Active Task State
3. Project Context
4. Decision Ledger

## Priority Order

1. System policies
2. Permanent restrictions
3. Current message
4. Active decisions
5. Active task
6. Project context
7. Recent conversation
8. Secondary history

## Token Budget

The default budget is `4096` estimated tokens. Older messages are excluded once the budget is reached.

## Decision Ledger

Decisions are stored as active or replaced records with:

- id
- timestamp
- source
- status
- scope
- reason
- confidence
- previous_decision_id

This lets ANN detect when a new instruction replaces a previous decision.
