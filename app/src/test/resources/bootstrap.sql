-- Credenciais exclusivas do contêiner descartável de testes.
CREATE ROLE tcc_migrator LOGIN PASSWORD 'migration-test';
CREATE ROLE tcc_app LOGIN PASSWORD 'application-test';
CREATE SCHEMA tcc AUTHORIZATION tcc_migrator;
GRANT USAGE ON SCHEMA tcc TO tcc_app;
