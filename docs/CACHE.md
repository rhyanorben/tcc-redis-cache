# Cache das páginas de pedidos

Cache-aside opcional da resposta paginada inteira, implementado com Spring Data Redis/Lettuce e JSON tipado. Está desligado por padrão e ainda não foi implantado nas VMs.

| Configuração | Leitura |
| --- | --- |
| `CACHE_ENABLED=false` | Consulta PostgreSQL; não cria conexão Redis nem tenta invalidá-lo |
| `CACHE_ENABLED=true` | Consulta Redis; em falta, carrega PostgreSQL e armazena a página com TTL |

O contrato HTTP é igual nos dois modos. Um acerto evita a transação PostgreSQL; uma falta mantém o snapshot descrito no [contrato](IMPLEMENTACAO.md). `ConsultaPedidosService` seleciona o caminho, `PedidoService` consulta o banco e `RedisPaginaCache` implementa o cache.

## Chaves e invalidação

```text
tcc:v1:tenant:{42}:pedidos:generation
tcc:v1:tenant:{42}:pedidos:<UUID>:page:0:size:20
```

Empresa, versão UUID, página e tamanho separam os resultados. Criar um pedido ou alterar seu status troca a versão da empresa **após o commit**, invalidando logicamente suas páginas e contagens. Rollback não invalida. Páginas antigas expiram pelo TTL; não há varredura de chaves nem limpeza global. O TTL começa na gravação e não é renovado por leituras.

Scripts Lua verificam atomicamente a versão ao ler e gravar páginas. Uma consulta iniciada antes da invalidação pode retornar seu snapshot antigo, mas não preenche uma versão nova. A chave de versão não expira; se for expulsa por `allkeys-lru`, um UUID novo impede reutilizar páginas antigas.

## Consistência e falhas

- Não há leitura linearizável entre PostgreSQL e Redis: existe uma janela entre commit e invalidação, e requisições em andamento podem terminar depois da escrita.
- Erros de conexão, timeout ou conteúdo inválido levam a consulta do PostgreSQL. Erros de negócio e banco continuam sendo propagados; erros de banco e respostas 404 não são armazenados.
- Se a invalidação falhar após commit, um marcador em memória mantém a empresa consultando o banco até reparar sua versão. Cada tentativa usa um UUID novo; a reparação remove o marcador correspondente. Uma falha prolongada mantém uma entrada por empresa afetada.
- A reparação funciona em uma instância. Os marcadores não são duráveis nem compartilhados: um encerramento entre commit e invalidação pode deixar páginas antigas até o TTL. Não há outbox, coordenação entre instâncias ou proteção contra consultas simultâneas à mesma página fria.
- SQL direto, geração de dados, restaurações e escritas com cache desligado não invalidam Redis. Antes de reabilitá-lo, use um namespace novo. Também troque o namespace ao mudar consulta/formato; não compare instâncias escrevendo simultaneamente na mesma base com cache ligado e desligado.

Redis não participa de `/actuator/health`; a API depende do PostgreSQL. Falhas de cache geram contadores e um aviso limitado a um por 30 segundos por instância, sem credenciais ou conteúdo. Não há circuit breaker: durante falhas, requisições ainda podem pagar timeouts de vários comandos.

## Configuração

| Variável | Padrão | Regra |
| --- | --- | --- |
| `CACHE_ENABLED` | `false` | Habilita Redis |
| `CACHE_NAMESPACE` | `tcc:v1` | `tcc:` seguido de 1–60 letras, dígitos, `:`, `_` ou `-` |
| `CACHE_TTL` | `60s` | De 1ms a 1h |
| `CACHE_TIMEOUT` | `200ms` | De 1ms a 5s por conexão/comando; não limita a requisição inteira |
| `REDIS_HOST` | `10.10.10.30` | Endereço Redis |
| `REDIS_PORT` | `6379` | Porta Redis |
| `REDIS_USER` | `app` | Usuário da ACL |
| `REDIS_PASSWORD` | Sem padrão | Obrigatória com cache ativo; fornecida por secret |

São valores iniciais, ainda sem calibração de desempenho.

## Configuração Docker preparada

O Compose base continua sem credencial Redis da aplicação. As sobreposições adicionam:

| Arquivo | Efeito |
| --- | --- |
| `infra/redis/compose.app-user.yaml` | Secret `redis_app_password` e usuário restrito `app` |
| `infra/app/compose.cache.yaml` | Cache habilitado e secret montado como `REDIS_PASSWORD` |

O script Redis preserva o usuário administrativo `default`. O usuário `app` usa hash SHA-256, chaves `~tcc:*` e permissões `+@connection +get +set +eval +evalsha`. A ACL limita o prefixo da aplicação; não separa usuários finais por empresa.

Na implantação autorizada, guarde a mesma senha nova em `secrets/redis_app_password.txt` nas pastas Redis e app. Ela deve ter ao menos 32 caracteres, diferir da administrativa e ser legível pelo usuário do contêiner, com diretório local 700. Não coloque senhas em `.env`, YAML ou Git. Primeiro valide a API sem cache; habilitar as sobreposições com `up` recria serviços e altera a ACL.

Na raiz do repositório, valide apenas a configuração:

```sh
docker compose --env-file infra/redis/.env.example \
  -f infra/redis/compose.yaml -f infra/redis/compose.app-user.yaml config --quiet

docker compose --env-file infra/app/.env.example \
  -f infra/app/compose.yaml -f infra/app/compose.cache.yaml config --quiet
```

## Métricas e testes

| Contador Micrometer | Significado |
| --- | --- |
| `tcc.cache.requests`, `result=hit\|miss\|fallback` | Acerto, falta ou desvio por falha/pendência |
| `tcc.cache.errors` | Falhas Redis/serialização; pode haver várias por requisição |
| `tcc.cache.invalidations` | Trocas de versão concluídas, incluindo reparações |
| `tcc.cache.discarded_writes` | Páginas descartadas por versão alterada ou invalidação pendente |

Não há tag por empresa nem endpoint de métricas exposto por padrão. Um miss pode terminar em erro de negócio; esses contadores não equivalem a respostas HTTP bem-sucedidas. A coleta externa está pendente.

A suíte descartável verifica equivalência da resposta, acertos sem banco, separação por empresa/página/tamanho, commit, rollback, TTL, corridas de preenchimento, perda de versão, JSON inválido, ACL e recuperação após pausa do Redis. O cenário sem cache verifica ausência de conexão Redis. Execução: [app/README.md](../app/README.md).
