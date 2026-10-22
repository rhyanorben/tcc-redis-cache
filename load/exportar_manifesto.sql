\set ON_ERROR_STOP on
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL search_path = tcc, pg_catalog;
COPY (
    WITH empresas AS (
        SELECT id, nome
        FROM empresa
        WHERE starts_with(nome, 'TCC-' || :'lote' || ' Empresa ')
    ), contagens AS MATERIALIZED (
        SELECT e.id, e.nome,
               (SELECT count(*) FROM cliente c WHERE c.tenant_id = e.id) AS clientes,
               (SELECT count(*) FROM pedido p WHERE p.tenant_id = e.id) AS pedidos,
               (SELECT count(*) FROM item_pedido i WHERE i.tenant_id = e.id) AS itens
        FROM empresas e
    )
    SELECT c.id AS tenant_id, c.nome AS empresa_nome,
           c.clientes AS total_clientes, c.pedidos AS total_pedidos,
           c.itens AS total_itens,
           row_number() OVER (PARTITION BY c.id ORDER BY p.id) - 1 AS slot,
           p.id AS pedido_id, p.status AS pedido_status
    FROM contagens c
    CROSS JOIN LATERAL (
        SELECT id, status FROM pedido
        WHERE tenant_id = c.id AND status = 'ABERTO'
        ORDER BY id
        LIMIT 20
    ) p
    ORDER BY c.id, p.id
) TO STDOUT WITH (FORMAT CSV, HEADER true);
COMMIT;
