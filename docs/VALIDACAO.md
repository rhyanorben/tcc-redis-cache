# Validação do alinhamento experimental

## Projeto

O repositório de desenvolvimento fica em `/home/rhyanorben/Documentos/RhyanPessoal/tcc-redis-cache`. A implantação de 20/10/2026 usou o código da API no commit `b1112e254d41fc3f15a41aff67b19a68ba922ddc`; seus registros e ajustes de documentação permanecem separados dos resultados da campanha.

| Verificação | Resultado | Data |
| --- | --- | --- |
| API, cache, arquitetura e configuração Java | 41 testes aprovados em PostgreSQL/Redis locais descartáveis; fontes Java preservadas desde essa validação | 17/10/2026 |
| Gerador de dados | 9 testes Python aprovados | 20/10/2026 |
| Coleta e resumo do monitoramento | 35 testes Python aprovados | 20/10/2026 |
| Manifesto, matriz, proteções e consolidação | 9 testes Python aprovados | 20/10/2026 |
| Distribuição da carga | Suíte Node aprovada | 20/10/2026 |
| Configurações Compose de app, Redis e PostgreSQL | Validação das configurações aprovada, sem iniciar serviços | 20/10/2026 |
| Script k6 1.6.0 | Teste local de dois segundos, 25 usuários, leituras e alterações de status, sem erros de contrato ou HTTP | 20/10/2026 |

O teste k6 utilizou uma API simulada e IDs fictícios, sem PostgreSQL ou Redis reais. Seu resumo contém `smoke_test=true` e `valid_for_campaign=false`; não pode ser consolidado como resultado científico. A validação comprova o funcionamento do script, sem estabelecer desempenho da API.

O gerador prepara SQL com três itens por pedido e valida contagens e totais antes do commit. A carga completa de 8.500.100 registros e a restauração foram conferidas em 22/10; veja o registro abaixo.

## Ambiente

As consultas de 17/10 e do início de 20/10 encontraram as VMs desligadas. Após o usuário informar que estavam funcionando e autorizar os procedimentos, a API foi implantada em 20/10. O [registro das VMs](../infra/DEPLOYMENT.md) preserva a sequência das intervenções.

| Verificação nas VMs | Resultado |
| --- | --- |
| API sem cache | 357 checagens e 30 requisições aprovadas |
| API com cache | 104 checagens e 47 requisições aprovadas |
| Contrato e isolamento | DTOs, totais, paginação, ordenação, limites e rejeição de vínculos entre empresas confirmados |
| Cache | Respostas iguais entre modos; falta seguida de acerto; invalidação após mudança real; repetição do status sem invalidação; outra empresa preservada |
| PostgreSQL | Flyway V1 concluída; usuário runtime consulta pedidos, sem acesso ao histórico Flyway ou criação no schema |
| Redis | 1 GiB, `allkeys-lru`, sem persistência; TTL próximo de 60 s e ACL restrita confirmados |
| Rede privada — 20/10 | API em `10.10.10.10:8080`; gerenciamento somente no loopback da tcc-app, porta 8081 |
| Ethernet — 21/10 | GET pela tcc-load em `10.20.20.10:8080` retornou 200 e três pedidos; SSH do host/app para o gerador confirmado |
| Restrição experimental — 21/10 | Portas 5432, 6379 e 8081 recusadas no IP experimental, inclusive a partir da tcc-load; internet original preservada |

Foram criadas duas empresas, dois clientes, seis pedidos e 18 itens do lote `TCC-validacao-f963091e25334c2d`. As empresas receberam IDs 1 e 2 nesta execução; esses valores não devem ser presumidos em novas cargas. Os relatórios e o manifesto estão em `results/implantacao-20261020/`, ignorados pelo Git. São verificações funcionais reais, sem significado de medição de desempenho.

Para repetir a validação, execute na tcc-app o procedimento de [infra/app/README.md](../infra/app/README.md), com arquivos de saída e manifesto novos. A primeira fase cria empresas próprias com a API sem cache; a segunda reutiliza esse manifesto com cache ativo e altera um pedido. Não repita isoladamente a fase de cache sobre o mesmo manifesto, pois seu estado original já foi modificado.

A [Ethernet experimental](../infra/network/ETHERNET.md) foi validada em 21/10 e permaneceu funcional após a inicialização de 22/10. O binário nativo k6 2.3.0 permanece instalado; desde 22/10 o executor usa o contêiner 1.6.0 fixado em [VERSIONS.md](../VERSIONS.md). O backup anterior à implantação é histórico; a preparação atual utiliza uma nova referência completa, com restauração validada. A campanha completa permanece pendente.

## Texto do TCC

[AJUSTES_TEXTO_TCC.md](AJUSTES_TEXTO_TCC.md) registra as substituições propostas. O usuário informou que aplicou os ajustes no documento. Esta implantação não altera o PDF nem essas propostas.

## Conferência final — 22/10/2026

Rede e serviços permaneceram disponíveis após a inicialização de hoje; as rotinas dos três coletores produziram uma amostra real válida. Naquela conferência, ainda pendiam espaço planejado, Docker/k6 de referência na geradora, base completa, automação e piloto; a preparação posterior está registrada a seguir. A [conferência final](CONFERENCIA_FINAL.md) registra recursos, disco, relógios e as trocas pontuais no PDF; evidências sem credenciais em `results/conferencia-20261022/`, ignoradas pelo Git.


## Preparação posterior e piloto — 22/10/2026

| Verificação | Resultado |
| --- | --- |
| Base completa | 100 empresas, 500.000 clientes, 2.000.000 pedidos e 6.000.000 itens no banco dedicado |
| Restauração | Referência restaurada em cópia independente; contagens e estados iniciais conferidos; mesma referência restaurada antes de cada caso |
| Geradora | Docker e imagem k6 1.6.0 fixada preparados na tcc-load |
| Automação local | 35 testes de monitoramento, nove de carga e dez de proteções/sessões aprovados |
| Piloto real | Par 90/10, 25 usuários, cache desligado/ligado: duas medições completas de 300 s, sem erros, com restauração e coleta válidas |

O banco anterior permanece com dois clientes, seis pedidos e 18 itens em duas empresas. A [preparação e o piloto](PREPARACAO_E_PILOTO.md) sucedem as pendências da conferência inicial desta data. Os arquivos brutos ficam em `results/piloto-20261022/`, fora do Git. Um par não fornece a consolidação das cinco repetições; a campanha permanece pendente.
