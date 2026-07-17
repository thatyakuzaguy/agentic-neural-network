INSERT INTO audit_events (event_id, event_type, actor, message, metadata)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'system.seed',
    'DatabaseSeeder',
    'Seeded Agentic Engineering Network baseline audit event.',
    '{"environment":"local"}'
)
ON CONFLICT (event_id) DO NOTHING;
