# API de pedidos

[Estrutura, modelo e contrato](../docs/IMPLEMENTACAO.md) · [Cache](../docs/CACHE.md) · [Implantação](../infra/app/README.md)

## Compilar e testar

Na raiz do repositório, com Java 21, Maven 3.6.3+, Python 3 e Docker acessível:

```sh
mvn -f app/pom.xml verify
```

A suíte reúne testes de arquitetura e de integração com HTTP real, PostgreSQL e Redis descartáveis. Verifica usuários separados de migração e execução, isolamento por empresa, paginação, integridade e cache com a ACL real do projeto. Não acessa as VMs e falha se Docker estiver indisponível.

## Executar

Em ambiente já provisionado, forneça `DB_URL`, `DB_USER` e `DB_PASSWORD` por um mecanismo local seguro:

```sh
java -jar app/target/pedidos-0.1.0-SNAPSHOT.jar
```

O padrão usa `tcc_app`, sem executar Flyway ou conectar ao Redis. Hibernate apenas valida o schema existente; não cria nem altera tabelas. As migrações usam `tcc_migrator` numa execução separada com `FLYWAY_ENABLED=true` e `SPRING_MAIN_WEB_APPLICATION_TYPE=none`. O [Compose](../infra/app/README.md) fornece as senhas por arquivos secret.

## Exemplos HTTP

Após implantação, substitua os IDs `1` pelos IDs retornados na criação da empresa e do cliente:

```sh
curl -i -X POST http://10.10.10.10:8080/api/empresas \
  -H 'Content-Type: application/json' -d '{"nome":"Empresa A"}'

curl -i -X POST http://10.10.10.10:8080/api/clientes \
  -H 'tenantId: 1' -H 'Content-Type: application/json' -d '{"nome":"Cliente A"}'

curl -i -X POST http://10.10.10.10:8080/api/pedidos \
  -H 'tenantId: 1' -H 'Content-Type: application/json' \
  -d '{"clienteId":1,"itens":[{"descricao":"Item A","quantidade":2,"precoUnitario":12.35}]}'

curl -i 'http://10.10.10.10:8080/api/pedidos?page=0&size=20&sort=criadoEm,desc' -H 'tenantId: 1'

curl -i -X PATCH http://10.10.10.10:8080/api/pedidos/1/status \
  -H 'tenantId: 1' -H 'Content-Type: application/json' -d '{"status":"CONFIRMADO"}'
```

O último exemplo também exige o ID do pedido criado. O cabeçalho seleciona a empresa do laboratório; não autentica usuários.
