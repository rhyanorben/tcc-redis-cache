\set ON_ERROR_STOP on

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA public;

CREATE ROLE tcc_monitor LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS;

GRANT CONNECT ON DATABASE tcc TO tcc_monitor;
GRANT USAGE ON SCHEMA public TO tcc_monitor;
GRANT pg_read_all_stats TO tcc_monitor;

ALTER ROLE tcc_monitor SET default_transaction_read_only = on;
ALTER ROLE tcc_monitor IN DATABASE tcc SET search_path = pg_catalog, public;

COMMIT;

\password tcc_monitor
