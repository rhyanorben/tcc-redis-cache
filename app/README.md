# API de pedidos — cache opcional

Modelo e contrato: [docs/IMPLEMENTACAO.md](../docs/IMPLEMENTACAO.md). Implantação planejada: [infra/app/README.md](../infra/app/README.md).

## Compilar e testar

Requer Java 21, Maven 3.6.3+, Python 3 (para verificar o gerador de dados) e Docker acessível para Testcontainers:

```sh
mvn -f app/pom.xml verify
```

Os testes iniciam um PostgreSQL descartável e independente das VMs, aplicam a migração e fazem requisições HTTP reais. Usam usuário runtime sem DDL e migrador separado. Não configuram credenciais reais nem acessam os IPs experimentais. A suíte também usa Redis descartável com a ACL e o script reais do projeto para verificar o cache opcional. Não omitem testes silenciosamente quando Docker está indisponível.

Para executar fora de Docker, em ambiente já provisionado, configure `DB_URL`, `DB_USER` e `DB_PASSWORD` por um mecanismo local seguro e use:

```sh
java -jar app/target/pedidos-0.1.0-SNAPSHOT.jar
```

Flyway fica desabilitado na execução comum. Para aplicar migrações, use credenciais do migrador com `FLYWAY_ENABLED=true` e `SPRING_MAIN_WEB_APPLICATION_TYPE=none`, em uma execução separada antes de iniciar a API. Não use `tcc_admin` como usuário runtime. O Compose fornece `DB_PASSWORD` por arquivo secret, sem senha no YAML.

Exemplo após implantação, usando IDs reais retornados pela criação:

```sh
curl -i -X POST http://10.10.10.10:8080/api/empresas \
  -H 'Content-Type: application/json' -d '{"nome":"Empresa A"}'

curl -i -X POST http://10.10.10.10:8080/api/clientes \
  -H 'X-Tenant-Id: 1' -H 'Content-Type: application/json' -d '{"nome":"Cliente A"}'

curl -i -X POST http://10.10.10.10:8080/api/pedidos \
  -H 'X-Tenant-Id: 1' -H 'Content-Type: application/json' \
  -d '{"clienteId":1,"itens":[{"descricao":"Item A","quantidade":2,"precoUnitario":12.35}]}'

curl -i 'http://10.10.10.10:8080/api/pedidos?page=0&size=20' -H 'X-Tenant-Id: 1'
```


## Cenários sem/com cache

Cache desligado por padrão, sem conexão Redis. A mesma API possui cache-aside opcional das páginas de pedidos. Consulte [docs/CACHE.md](../docs/CACHE.md) para variáveis, invalidação, métricas, testes e limites de consistência. A integração foi implementada no código e ainda não foi aplicada às VMs.
