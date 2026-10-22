# Registro das VMs — 15/10/2026

Preparação anterior executada via SSH com autorização. Não foram removidos dados ou serviços existentes. Este registro descreve aquela execução; não confirma o estado remoto atual.

| VM | Resultado registrado |
| --- | --- |
| tcc-postgres — 10.10.10.20 | Docker 29.9.1, Compose 5.6.0 e PostgreSQL 17.11 saudável |
| tcc-redis — 10.10.10.30 | Docker 29.9.1, Compose 5.6.0 e Redis 7.4.11 saudável |
| tcc-app — 10.10.10.10 | Clientes PostgreSQL/Redis instalados; API pendente |

## Arquivos e credenciais

Nas VMs de dados, cada serviço usa `/home/rhyan/tcc-infra/infra/postgres/` ou `/home/rhyan/tcc-infra/infra/redis/`. Os `.env` fixam os digests registrados em [VERSIONS.md](../VERSIONS.md).

Senhas distintas de 64 caracteres hexadecimais foram geradas sem reutilizar a senha SSH. Estão em `secrets/postgres_password.txt` e `secrets/redis_password.txt`, nas respectivas pastas das VMs. Os diretórios têm modo 700 e os arquivos 644 para leitura dos contêineres. As credenciais não foram versionadas nem incluídas neste registro.

## Validação executada

- Contêineres `healthy`, publicados nos respectivos IPs internos.
- Da tcc-app, PostgreSQL autenticado confirmou banco `tcc`, usuário `tcc_admin` e versão; Redis autenticado retornou `PONG`.
- PostgreSQL rejeitou senha inválida; Redis sem senha retornou `NOAUTH`.
- PostgreSQL confirmou persistência em `/var/lib/postgresql/data`, UTC e SCRAM-SHA-256.
- Redis confirmou 256 MiB, `allkeys-lru` e ausência de AOF/RDB.
- Portas dos bancos bloquearam o computador físico; SSH permaneceu acessível.
- Restrição de rede habilitada nas duas VMs; reinicialização ainda não testada.

## Consultar o ambiente

Na VM PostgreSQL, ou trocando a primeira pasta por `redis` na outra VM:

```sh
cd ~/tcc-infra/infra/postgres
sudo docker compose ps
sudo docker compose logs --tail=100
sudo systemctl status tcc-network-guard.service --no-pager
sudo iptables -vnL DOCKER-USER
```

A administração usa `sudo`; o usuário não foi adicionado ao grupo Docker. A instalação seguiu o [repositório oficial para Ubuntu](https://docs.docker.com/engine/install/ubuntu/), sem atualização geral do sistema.

Pendem implantação da API, usuários e migrações de negócio, ACL Redis da aplicação, backup/restauração, teste de persistência após reinício e dimensionamento definitivo. Nenhum ensaio de carga foi executado.


## Alinhamento experimental — 16/10/2026

Intervenção posterior autorizada, preservando os registros e os volumes existentes. A data desta seção corresponde à execução, não à revisão desta documentação.

| VM | Confirmação |
| --- | --- |
| tcc-app | 2 vCPU e 4 GiB; API ainda não implantada |
| tcc-postgres | 2 vCPU e 4 GiB; PostgreSQL 17.11 e extensão `pg_stat_statements` 1.11 |
| tcc-redis | 1 vCPU e 2 GiB; Redis 7.4.11, `maxmemory=1gb`, `allkeys-lru`, sem RDB/AOF |

PostgreSQL foi reiniciado com `pg_stat_statements` carregado, preservando o volume de dados. A configuração anterior foi copiada com identificação `20261016T125141Z`. A role de monitoramento foi provisionada para consulta de estatísticas, sem escrita nas tabelas de negócio; sua credencial fica somente na VM PostgreSQL, em `secrets/monitor_password.txt`, com modo 600. Não é uma credencial da API e não deve ser versionada.

O limite Redis foi ajustado em execução para 1 GiB por `CONFIG SET` e persistido no arquivo de configuração, sem reinício, limpeza de chaves ou alteração de persistência. A configuração anterior foi copiada com identificação `20261016T125215Z`. Isso atualiza o limite de 256 MiB registrado na seção histórica de 15/10.

Não foram aplicadas migrações de negócio, carregada a base de 8,5 milhões de registros, implantada a API ou executada campanha de carga. ACL Redis da aplicação, roles de negócio, backup/restauração da base experimental e integração dos hooks continuam pendentes de implantação e validação. A configuração local preparada de coleta/carga não significa que esses procedimentos foram executados remotamente.


## Consulta após reinício do host — 17/10/2026

A consulta ao libvirt após reinício do computador físico mostrou as três VMs de serviço desligadas. A inicialização das VMs PostgreSQL e Redis foi bloqueada pela revisão automática de aprovação antes da execução; nenhuma VM foi iniciada e nenhum serviço foi alterado nesta data.

As configurações e validações de 16/10 permanecem como registro histórico. Não houve nova verificação ao vivo de PostgreSQL, Redis, credenciais, persistência ou recursos internos em 17/10. A retomada do ambiente continua pendente.

No computador de desenvolvimento, em contêineres Docker descartáveis, os 41 testes Java e os nove testes do gerador passaram em 17/10/2026. Esses testes verificam correção funcional e não constituem resultados de desempenho nem uma validação das VMs.


## Consulta de estado — 20/10/2026

A consulta somente leitura ao libvirt confirmou `tcc-app`, `tcc-postgres` e `tcc-redis` desligadas. Não foram iniciadas VMs nem revalidados os serviços por SSH. As intervenções de 16/10 permanecem como histórico; a confirmação dos serviços em execução depende de autorização específica para ligar as VMs.


## Retomada e implantação da API — 20/10/2026

Após o usuário informar que as três VMs estavam em funcionamento e autorizar os procedimentos, a implantação foi executada via SSH. As consultas anteriores desta data permanecem como histórico; o estado final abaixo as sucede.

| VM | Estado confirmado |
| --- | --- |
| tcc-app | API em Docker em `10.10.10.10:8080`; gerenciamento publicado somente em `127.0.0.1:8081` |
| tcc-postgres | PostgreSQL 17.11; schema `tcc`, usuários separados e migração Flyway V1 aplicada |
| tcc-redis | Redis 7.4.11; usuário `app` restrito, 1 GiB, `allkeys-lru`, sem AOF/RDB |

Docker Engine 29.9.1, Compose 5.6.0, containerd 2.4.2 e Buildx 0.38.0 foram instalados na tcc-app, sem atualização geral do sistema. O código da API fica em `/home/rhyan/tcc-app`, a partir do commit `b1112e254d41fc3f15a41aff67b19a68ba922ddc`. A imagem `tcc-pedidos:0.1.0`, com Temurin 21.0.12.1+1, foi a mesma nos dois modos; seu ID consta em [VERSIONS.md](../VERSIONS.md).

Antes das alterações foi criado `~/tcc-infra/infra/postgres/backups/antes-api-20261020T113919Z/tcc.dump`. O backup não foi restaurado e não representa a base inicial da campanha. O provisionamento criou `tcc_migrator` e `tcc_app` sem privilégios de superusuário, criação de banco ou criação de roles; o migrador é proprietário do schema `tcc`. O script foi revisado para definir as senhas antes do commit. A API confirmou acesso a pedidos, sem acesso ao histórico Flyway ou permissão de criação no schema.

As credenciais de negócio na VM PostgreSQL têm modo 600. Na tcc-app, os secrets têm modo 640, proprietário `rhyan` e grupo numérico 10001, com diretório 700. A senha da aplicação Redis tem modo 600 na VM Redis e 640 na tcc-app. Credenciais não foram registradas em Git ou nos relatórios.

A configuração Redis anterior foi preservada com identificação `acl-app-20261020T114431Z`; o serviço foi recriado após confirmar `DBSIZE=0`. A ACL da aplicação autenticou e negou acesso fora de `tcc:*` e `FLUSHALL` por verificação de permissão, sem executar esse comando. Ao administrar o Redis, use `-f compose.yaml -f compose.app-user.yaml`; na API com cache, use `-f compose.yaml -f compose.cache.yaml`.

A validação sem cache aprovou 357 checagens em 30 requisições; com cache, 104 em 47 requisições. Confirmou equivalência das respostas, isolamento, paginação, falta seguida de acerto, invalidação após mudança real e ausência de invalidação ao repetir o status. Uma página recém-gravada apresentou 59.880 ms de prazo restante. Foram mantidos dois clientes, seis pedidos e 18 itens nas duas empresas do lote `TCC-validacao-f963091e25334c2d`, IDs 1 e 2 nesta execução.

O estado final mantém cache habilitado, namespace `tcc:vm-validacao-20261020`, TTL de 60 s e timeout de 200 ms. Os relatórios ficam em `results/implantacao-20261020/`, ignorados pelo Git; veja [VALIDACAO.md](../docs/VALIDACAO.md). Não foram carregados os 8,5 milhões de registros nem executados piloto ou campanha. Host 2, restauração da base experimental e integração dos hooks remotos continuam pendentes.


## Ethernet do computador 1 — 21/10/2026

A intervenção autorizada criou a bridge persistente `br-tcc`, com `10.20.20.1/24`, e vinculou a Ethernet `enp4s0`, em enlace de 1 Gbps e duplex completo. A rede experimental não recebe gateway, DNS ou IPv6; a internet permanece em `wlo1`, pelo gateway `192.168.10.1`. O Wi-Fi e `50-cloud-init.yaml` do host foram comparados com suas cópias e preservados.

A tcc-app recebeu uma segunda NIC virtio, `enp7s0`, MAC `52:54:00:20:20:10`, no XML ativo e persistente. O novo arquivo Netplan aplica `10.20.20.10/24` por MAC, sem DHCP, gateway ou DNS; a interface privada permanece inalterada. `compose.ethernet.yaml` acrescenta a publicação HTTP experimental, preservando `10.10.10.10:8080` e `127.0.0.1:8081`. Somente a aplicação foi recriada, com a mesma imagem e cache habilitado. Nenhuma regra manual de firewall foi acrescentada; Docker atualizou as regras das publicações.

| Verificação | Resultado |
| --- | --- |
| HTTP pelo computador 1 | Endereços privado e experimental retornaram 200, com conteúdo igual |
| HTTP pela tcc-load | GET em `10.20.20.10:8080/api/pedidos`, com `tenantId: 1`, retornou 200 e três pedidos |
| tcc-app → PostgreSQL e Redis | TCP privado e operação da aplicação preservados; falta seguida de acerto, sem fallback |
| Internet e rotas | HTTPS funcional; saída original preservada no host e na tcc-app |
| Portas no IP experimental | 5432, 6379 e 8081 recusadas |
| Computador 2 e tcc-load | ARP confirmado nos dois endereços; host e tcc-app alcançam a tcc-load por ping e TCP 22 |

Inicialmente não havia respostas ARP. O driver `r8168` 8.052.01 apresentava transmissão e interrupções praticamente paradas; reassociá-lo não resolveu. A troca para o `r8169` do kernel restaurou imediatamente a comunicação. O pacote `driverctl` 0.115-1 foi instalado para persistir a escolha somente no dispositivo PCI `0000:04:00.0`, preservando o driver anterior para reversão. O Windows respondeu ARP, embora não tenha respondido ICMP; a tcc-load respondeu ping e SSH. Não foi necessário liberar ICMP no Windows.

Na tcc-app, a rota para a tcc-load usa `enp7s0`, com origem `10.20.20.10`; no gerador, a rota para a API usa `ens37`, com origem `10.20.20.40`. O GET remoto confirmou o caminho completo pela Ethernet. Não houve ensaio de carga ou reinicialização para testar persistência. As configurações persistidas, cópias de segurança e reversão estão em [ETHERNET.md](network/ETHERNET.md).


## Base completa e piloto — 22/10/2026

A preparação autorizada ampliou somente o volume lógico PostgreSQL para 32 GiB, dentro do disco virtual existente. O banco `tcc` anterior foi preservado e copiado para backup; a migração V1 e os 8.500.100 registros foram aplicados em `tcc_experimento`. `compose.experiment.yaml` seleciona esse destino sem alterar o `.env` anterior ou a imagem da API.

A referência `base-v1.dump` foi restaurada em uma base temporária, com todas as contagens conferidas, e copiada para a geradora no computador 2 com o mesmo hash. Docker 29.9.1, Compose 5.6.0 e o contêiner k6 1.6.0 fixado foram preparados na tcc-load. Os agentes de preparação usam SSH/sudo autenticado manualmente em sessões temporárias, sem novas chaves permanentes ou regras sudo sem senha.

Par 90/10, 25 usuários, cache desligado/ligado: duas medições completas de 300 s, sem erros, com restauração e coleta válidas O [registro da preparação](../docs/PREPARACAO_E_PILOTO.md) reúne espaço, índices, recuperação e evidências; a [operação dos hooks](experiment/README.md) descreve autenticação, repetição e reversão. A campanha completa não foi iniciada.
