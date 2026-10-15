# Banco de dados

As [migrações Flyway](../app/src/main/resources/db/migration/) são empacotadas com a aplicação. Para evoluir o schema, crie uma nova versão; não duplique nem altere migrações já aplicadas.

- [Modelo inicial](../app/src/main/resources/db/migration/V1__modelo_multiempresa.sql): empresa, cliente, pedido e item_pedido.
- [Provisionamento](../infra/postgres/provision-app.sql): migrador proprietário do schema e usuário da API sem DDL.
- [Modelo e geração de dados](../docs/IMPLEMENTACAO.md).
- [Procedimento de implantação](../infra/app/README.md).

Usuários da aplicação, migrações e carga de dados ainda não foram aplicados às VMs.
