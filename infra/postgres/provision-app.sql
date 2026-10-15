-- Executar uma única vez, como administrador, antes de Flyway.
-- Não substitui roles existentes; pare se qualquer comando falhar.
\set ON_ERROR_STOP on
BEGIN;
CREATE ROLE tcc_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE tcc_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE SCHEMA tcc AUTHORIZATION tcc_migrator;
GRANT CONNECT ON DATABASE tcc TO tcc_migrator, tcc_app;
GRANT USAGE ON SCHEMA tcc TO tcc_app;
-- As migrações concedem acesso somente às tabelas de negócio.
COMMIT;
-- Prompts sem senha escrita em SQL ou histórico.
\password tcc_migrator
\password tcc_app
