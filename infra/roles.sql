-- Run once as the migration owner. Set random passwords through your secret manager.
-- app role is never an owner, superuser, or BYPASSRLS role.
CREATE ROLE medflow_app NOLOGIN NOSUPERUSER NOBYPASSRLS;
CREATE ROLE medflow_auth NOLOGIN NOSUPERUSER BYPASSRLS;
CREATE ROLE medflow_worker NOLOGIN NOSUPERUSER BYPASSRLS;
GRANT USAGE ON SCHEMA public TO medflow_app,medflow_auth,medflow_worker;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO medflow_app;
REVOKE ALL ON identity_mappings,auth_sessions FROM medflow_app;
GRANT INSERT ON identity_mappings TO medflow_app;
REVOKE UPDATE,DELETE ON audit_logs,network_events FROM medflow_app;
REVOKE ALL ON alembic_version FROM medflow_app;
GRANT SELECT ON users,identity_mappings TO medflow_auth;
GRANT SELECT,INSERT,DELETE ON auth_sessions TO medflow_auth;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO medflow_worker;
-- Separate login principals inherit ONLY their designated role.
-- RLS context is set inside trusted server transactions, never from browser input.
