# Banco de dados

As migrações têm uma única fonte em [`app/src/main/resources/db/migration/`](../app/src/main/resources/db/migration/), para serem empacotadas com a aplicação e executadas pelo Flyway. Não duplique ou altere migrações já aplicadas; crie uma próxima versão.

- [Migração inicial: empresa, cliente, pedido e item_pedido](../app/src/main/resources/db/migration/V1__modelo_multiempresa.sql).
- [Provisionamento inicial dos usuários](../infra/postgres/provision-app.sql).
- [Modelo e estratégia de paginação](../docs/IMPLEMENTACAO.md).
- [Gerador de dados experimentais](../scripts/gerar_base.py).
- [Procedimento de migração e implantação](../infra/app/README.md).

O provisionamento, as migrações e a carga de dados ainda não foram aplicados às VMs. A geração do arquivo SQL não altera banco algum.
