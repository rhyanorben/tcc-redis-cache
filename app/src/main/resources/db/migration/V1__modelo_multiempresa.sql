CREATE TABLE empresa (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome varchar(160) NOT NULL CHECK (length(trim(nome)) > 0),
    criado_em timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE cliente (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id bigint NOT NULL REFERENCES empresa(id),
    nome varchar(160) NOT NULL CHECK (length(trim(nome)) > 0),
    criado_em timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id)
);

CREATE TABLE pedido (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id bigint NOT NULL REFERENCES empresa(id),
    cliente_id bigint NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'ABERTO'
        CHECK (status IN ('ABERTO', 'CONFIRMADO', 'CANCELADO')),
    total numeric(19, 2) NOT NULL CHECK (total >= 0),
    criado_em timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, cliente_id) REFERENCES cliente(tenant_id, id)
);

CREATE TABLE item_pedido (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id bigint NOT NULL REFERENCES empresa(id),
    pedido_id bigint NOT NULL,
    descricao varchar(200) NOT NULL CHECK (length(trim(descricao)) > 0),
    quantidade integer NOT NULL CHECK (quantidade BETWEEN 1 AND 1000000),
    preco_unitario numeric(12, 2) NOT NULL CHECK (preco_unitario >= 0),
    FOREIGN KEY (tenant_id, pedido_id) REFERENCES pedido(tenant_id, id)
);

CREATE INDEX idx_pedido_tenant_criado_id ON pedido (tenant_id, criado_em DESC, id DESC);
CREATE INDEX idx_pedido_tenant_cliente ON pedido (tenant_id, cliente_id);
CREATE INDEX idx_item_pedido_tenant_pedido ON item_pedido (tenant_id, pedido_id);

GRANT SELECT, INSERT, UPDATE ON empresa, cliente, pedido, item_pedido TO tcc_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA tcc TO tcc_app;
