# ANN Conversational Chat

Desktop Chat now routes natural language through the Conversation Orchestrator.

## User Experience

The user can write requests such as:

- "Revisa este proyecto y dime qué falta."
- "Arregla el login, pero no toques la base de datos."
- "Ejecuta solo los tests relacionados."
- "No apliques todavía el parche."
- "Haz una revisión de seguridad."

ANN converts those into:

1. intent contract
2. validated route
3. agent-specific prompts
4. existing pipeline execution or approval block
5. truthful final response

## Technical Details

Each run writes contract and routing artifacts into the run directory. The default UI can stay simple, while technical diagnostics can inspect the JSON artifacts.

## Truthfulness

The user response distinguishes:

- performed
- proposed
- pending approval
- blocked
- simulated
- failed
- not checked

ANN must not claim tests passed when no test evidence exists.
