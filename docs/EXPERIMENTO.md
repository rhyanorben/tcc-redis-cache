# Protocolo experimental

Este documento preserva o protocolo 2, usado na campanha concluída. A revisão atual
altera somente a navegação e está descrita em [Paginação por visitas — protocolo 3](PAGINACAO_V3.md).

O protocolo 2 compara a mesma API com cache desligado e ligado na campanha `campanha-20261024-v2`. A [revisão de capacidade](REVISAO_CAPACIDADE.md) corrige a transação externa à consulta do cache e distingue recusa anterior à escrita de falha com estado incerto. A campanha de 23/10 permanece como registro da configuração anterior, sem aproveitamento das medições na nova campanha. O [guia em blocos](CAMPANHA_EM_BLOCOS.md) apresenta os comandos.

## Condições fixas

| Item | Definição |
| --- | --- |
| Modelo | `empresa`, `cliente`, `pedido`, `item_pedido`; tabelas compartilhadas, segregação por `tenant_id` |
| Base | 100 empresas, 5.000 clientes, 20.000 pedidos e 60.000 itens por empresa; 8.500.100 registros |
| Leitura | Página de 20 resumos de pedidos com cliente, sem itens; `criadoEm DESC, id DESC` |
| Empresas ativas | As mesmas 25 em todos os níveis de concorrência |
| Localidade | 80% das leituras nas primeiras 20% das páginas; restantes nas demais |
| Escrita | PATCH de status; um pedido exclusivo por usuário, alternando estados após confirmações |
| Redis | 1 GiB para entradas, `allkeys-lru`, sem persistência; TTL de 60 s, sem renovação na leitura |
| Invalidação | Troca de geração da empresa após commit; páginas antigas expiram pelo TTL |
| API | Instância e artefato únicos; pool de 10 conexões, espera de 5 s e recursos iguais nos dois modos |
| Admissão ao banco | Até 10 operações simultâneas, fila justa e espera máxima de 5 s, antes da transação |
| Aquecimento | 120 s somente de leitura, excluídos da análise |
| Medição | 300 s por execução |

Acertos no cache não abrem transação nem passam pela admissão ao banco. Ausências e desvios por falha consultam PostgreSQL em transação `REPEATABLE_READ`. O mesmo limite atende leituras que chegam ao banco e escritas, nos dois modos.

As 100 empresas compõem a base; somente 25 recebem tráfego, com 1, 2, 4, 10 ou 20 usuários por empresa. Isso não equivale a 100 empresas simultaneamente ativas. O cache não oferece leitura linearizável: há uma janela entre commit e invalidação; expiração, invalidação e expulsão por memória fazem parte do cenário. A VM Redis também precisa de memória para estruturas e buffers fora do limite das entradas.

## Base e verificação prévia

A base de referência, seu backup e manifesto foram preparados e validados na etapa registrada em [PREPARACAO_E_PILOTO.md](PREPARACAO_E_PILOTO.md). Preserve o mesmo backup, IDs reais, índices e volumes. A leitura não carrega os itens, mas eles permanecem na base e nas operações de negócio. Antes de gerar outra base, confira espaço, contagens, integridade, planos SQL e consumo de memória.

Testes funcionais e de integração verificam a implementação; não demonstram sua capacidade sob 500 usuários. Nenhum ensaio da revisão é iniciado pelo chat. O operador executa `--piloto`: o par original 90/10 com 500 usuários, nos dois modos, com a mesma semente e os tempos completos. A coleta fica separada e excluída da campanha. Após conferir seu ZIP, o operador inicia o bloco 1; sequências ficam para depois da conferência desse bloco. Pilotos e dados da implementação anterior não integram as cinco repetições da nova campanha.

## Matriz e pareamento

| Parâmetro | Valores |
| --- | --- |
| Leitura/escrita | 100/0, 90/10, 70/30, 50/50 |
| Usuários virtuais | 25, 50, 100, 250, 500 |
| Modos | Cache desligado e ligado |
| Repetições | 5 por combinação |
| Total | 200 execuções, em 100 pares e 20 blocos |

Cada par usa a mesma base, empresas, pedidos, páginas de referência, semente e parâmetros. A ordem dos modos é aleatorizada no plano. O protocolo 2 reutiliza a ordem e as sementes originais, mas recomeça todas as medições com a API revisada.

A carga mantém usuários concorrentes constantes, sem pausa programada entre operações. Cada grupo completo de 100 tentativas por usuário contém a proporção planejada; o último pode ficar incompleto. A semente reproduz decisões, não o total nem a intercalação das requisições. Recusas continuam sendo tentativas do perfil; não há repetição automática para forçar seu sucesso. O próximo PATCH mantém o estado desejado até uma confirmação válida, garantindo que a próxima escrita confirmada alterne o estado.

São no mínimo 23h20 de aquecimento/medição; restauração, drenagem, início dos serviços e exportação acrescentam tempo. Matriz, ritmo, limites e tratamento de falhas permanecem fixos durante toda a campanha.

## Preparação de cada execução

1. Encerre a carga anterior e espere as requisições terminarem.
2. Restaure o mesmo backup no banco isolado `tcc_experimento` e confira base e manifesto.
3. Selecione o modo do cache; preserve a imagem e todas as demais configurações. Aguarde a API pronta.
4. Esvazie fisicamente o Redis dedicado antes do aquecimento, inclusive no modo sem cache. Mudar somente o namespace preservaria memória e estatísticas anteriores.
5. Confira coletores, relógios, empresas e pedidos reservados para escrita.
6. Aqueça somente com leituras e drene as requisições antes da medição.
7. Capture contadores iniciais, execute 300 s e drene as requisições finais antes dos contadores finais.
8. Encerre os coletores e preserve logs, dados brutos, resumos e recibos.

Os [hooks das VMs](../infra/experiment/README.md) executam essas etapas em sessões temporárias autenticadas manualmente. A restauração foi validada separadamente. O banco original `tcc` permanece fora desse escopo.

## Erros e validade

Somente o HTTP 503 com tipo `urn:tcc:problem:database-capacity`, código `DATABASE_CAPACITY_EXCEEDED` e `operationApplied=false` comprova recusa pela admissão antes da transação. Conta como erro e recusa, sem invalidar automaticamente a medição. Não representa escrita aplicada nem sucesso.

Timeout, 500, 503 genérico ou corpo de escrita inválido mantêm resultado incerto: interrompa, preserve a tentativa e repita ambos os modos do par após nova restauração. HTTP 200 de leitura fora do contrato também interrompe; outros erros HTTP de leitura permanecem como desfechos da carga. Falha de preparação, coleta, relógio ou integridade, mudança dos recursos fixados e falta de espaço invalidam a execução.

O uso de recursos da geradora também é registrado; indícios de gargalo nela exigem revisão antes de continuar. Uma medição completa de saturação da aplicação pode ser válida e conter erros. Validade do procedimento não significa desempenho aceitável. O executor exige protocolo/schema 2, contadores coerentes e ausência de escrita incerta; dados anteriores não são combinados com os novos.

## Coleta e consolidação

| Medida | Fonte e tratamento |
| --- | --- |
| Média, mediana, p95 e p99 | k6; leitura/escrita separadas, com latências de sucesso próprias |
| Vazão | k6; tentativas e sucessos por segundo separados |
| Erros e recusas | k6; leitura/escrita e recusas de admissão identificadas |
| CPU e memória dos serviços | Docker; somente a janela de 300 s |
| Consultas ao banco | Deltas de `pg_stat_statements`, filtrados pela role `tcc_app` |
| Acertos, faltas e fallback de páginas | Deltas de contadores Micrometer da API |
| Memória e expulsões Redis | `INFO memory` e deltas de `INFO stats` |

O monitoramento roda localmente em cada VM, com conexões administrativas fora da carga. A API expõe somente `health` e `metrics` na porta administrativa 8081, restrita ao loopback. A role PostgreSQL de monitoramento não escreve nas tabelas de negócio. As estatísticas SQL são filtradas desde a restauração atual, sem zerar contadores globais.

Contadores precisam de amostras antes da medição e depois da drenagem. Recursos são amostrados a cada 5 s; a resolução não permite atribuição ao milissegundo. Relógios devem estar sincronizados. Ausência de fronteiras, reinício ou reset invalida a coleta. `monitoring/resumir.py` exige `--measurement-summary` para recortar a janela experimental; o escopo `collection` não serve como resultado de medição.

Calcule o acerto lógico como `hit / (hit + miss + fallback)` e apresente fallback separadamente. Uma falta pode terminar em erro HTTP. Hits/misses internos do Redis incluem comandos auxiliares e não equivalem ao acerto de páginas. Total de SQL também não equivale ao total de leituras HTTP.

Consolide cinco repetições por perfil, concorrência, modo e operação, preservando valores individuais, média, mediana e desvio-padrão amostral. Compare cada par e calcule variação percentual somente com denominadores válidos. p95/p99 resumidos por execução não são percentis de todas as requisições reunidas. Se não houver sucesso, sua latência é ausente; não atribua zero. A consolidação identifica as repetições disponíveis e usa somente pares disponíveis para essa métrica, sem substituir as cinco execuções obrigatórias.

Arquive tentativas incompletas e não as elimine silenciosamente. Registre código, digests, versões efetivas, recursos, base, índices, pool, admissão, TTL, timeout, sementes e ordem. Consulte [VERSIONS.md](../VERSIONS.md), [DEPLOYMENT.md](../infra/DEPLOYMENT.md) e [REVISAO_CAPACIDADE.md](REVISAO_CAPACIDADE.md).
