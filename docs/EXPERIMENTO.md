# Protocolo experimental

Este protocolo fixa as condições para comparar a mesma API com cache desligado e ligado. A API foi implantada e validada funcionalmente nas VMs em 20/10/2026. A base completa e os hooks remotos foram preparados em 22/10/2026; o [registro da preparação e do piloto](PREPARACAO_E_PILOTO.md) apresenta as evidências. A campanha completa permanece pendente.

## Condições fixas

| Item | Definição |
| --- | --- |
| Modelo | `empresa`, `cliente`, `pedido`, `item_pedido`; banco e schema compartilhados, segregação por `tenant_id` |
| Base | 100 empresas, 5.000 clientes, 20.000 pedidos e 60.000 itens por empresa; 8.500.100 registros |
| Leitura | `GET /api/pedidos`, página de 20 pedidos, `criadoEm DESC, id DESC`; resumo com cliente, sem carregar itens |
| Empresas ativas | As mesmas 25 empresas em todos os níveis de concorrência |
| Localidade | 80% das leituras sobre um conjunto fixo de 20% das páginas de cada empresa ativa; demais leituras sobre as outras páginas |
| Escrita | `PATCH` de status; cada usuário possui um pedido exclusivo e alterna estados para produzir alterações reais |
| Redis | 1 GiB de `maxmemory`, `allkeys-lru`, sem RDB/AOF, TTL fixo de 60 s sem renovação na leitura |
| Invalidação | Troca de geração da empresa após commit; páginas anteriores expiram pelo TTL |
| API | Instância única; mesmo artefato, pool, índices, timeout e recursos nos dois modos |
| Aquecimento | 2 minutos somente de leitura, excluídos da análise |
| Medição | 5 minutos por execução |

As 100 empresas compõem a base; 25 recebem tráfego para manter constante a quantidade de empresas ativas. Distribua os usuários igualmente entre elas: 1, 2, 4, 10 ou 20 usuários por empresa. Não compare esses resultados como uma avaliação de 100 empresas simultaneamente ativas.

O cache tem uma janela entre commit e invalidação e não oferece leitura linearizável. Seu TTL limita a retenção de versões antigas; expirações, invalidações e expulsões por memória fazem parte do cenário avaliado. O limite Redis é inferior à memória total de sua VM: o processo também possui estruturas e buffers fora de `maxmemory`.

## Base e piloto

Gere a base uma vez em ambiente experimental isolado, confira totais, integridade e três itens por pedido. Confira espaço em disco, tamanho de tabelas e índices, planos SQL e consumo de memória antes da campanha. Não carregue milhões de registros sem essa verificação.

Exemplo de geração de SQL, sem conectar ou alterar o banco:

```sh
python3 scripts/gerar_base.py --empresas 100 --clientes-por-empresa 5000 \
  --pedidos-por-empresa 20000 --itens-por-pedido 3 --lote base-v1 \
  --saida /tmp/tcc-base-v1.sql
```

Use os IDs efetivamente gerados; eles não precisam começar em 1. A listagem consulta pedidos e clientes; os itens compõem a base e as operações de negócio, mas não são carregados pela leitura avaliada.

Após preparar a VM de carga, carregar a base e validar os coletores e hooks, execute um piloto curto. Confirme operações efetivas de escrita, ausência de erros de contrato, distribuição de páginas/empresas, diferença entre hit e miss e ausência de sobrecarga no gerador. O piloto valida o procedimento; não substitui as repetições finais nem fornece resultados da campanha.

## Campanha e pareamento

| Parâmetro | Valores |
| --- | --- |
| Leitura/escrita | 100/0, 90/10, 70/30, 50/50 |
| Usuários virtuais | 25, 50, 100, 250, 500 |
| Modos | Cache desligado e ligado |
| Repetições | 5 por combinação |
| Total | 200 execuções, organizadas em 100 pares |

Cada par usa o mesmo conjunto de dados, empresas, pedidos de escrita, páginas de referência, semente e parâmetros. A ordem dos modos é aleatorizada e registrada no plano. A semente torna a seleção de operações reproduzível; por ser uma carga de usuários concorrentes com duração fixa, não garante o mesmo total de requisições ou intercalação entre os modos.

Os sete minutos de cada execução somam no mínimo 23h20. Restauração, início dos serviços, drenagem, verificação e exportação acrescentam tempo. Fixe também o ritmo da carga e os limites de erro antes do piloto e preserve-os na campanha.

## Preparação de cada execução

1. Pare a geração de carga e espere terminar todas as requisições anteriores.
2. Restaure uma cópia da mesma base de referência no banco experimental isolado. Confira o resultado antes de prosseguir.
3. Selecione o modo da API; mantenha a imagem e todas as outras configurações constantes. Espere a API ficar pronta.
4. Limpe fisicamente o banco Redis dedicado ao experimento, antes do aquecimento. Mudar apenas o namespace não libera páginas antigas e não estabelece a mesma condição inicial de memória e expulsões.
5. Verifique os coletores, os relógios e as referências de empresas e pedidos.
6. Execute o aquecimento somente com leituras. Drene suas requisições antes da janela de medição.
7. Registre os contadores iniciais, execute os 300 s de medição e drene as requisições finais antes dos contadores finais.
8. Guarde os arquivos originais, o plano e a identificação dos artefatos; encerre os coletores.

Backup, restauração, limpeza Redis e seleção do modo são integrações explícitas do executor. Os [hooks das VMs](../infra/experiment/README.md) usam sessões temporárias autenticadas manualmente e o banco dedicado `tcc_experimento`. A restauração foi validada em uma cópia independente antes do piloto. O executor recusa hooks ausentes e interrompe a execução diante de falhas; os [contratos](../load/hooks.example/README.md) permanecem como referência para outros ambientes.

## Coleta e limites de atribuição

`monitoring/coletar.py` deve ser executado localmente em cada VM de serviço, com acesso ao Docker local. Ele coleta recursos do contêiner, estatísticas SQL, `INFO` Redis ou métricas HTTP, conforme o serviço selecionado. As conexões administrativas ficam fora da carga medida.

| Medida | Fonte e tratamento |
| --- | --- |
| Latência média, mediana, p95 e p99 | k6, separando leitura e escrita; aquecimento excluído |
| Vazão e erros | k6, separando operações e requisições totais |
| CPU e memória | Docker de cada serviço; recortar pela janela de medição de 300 s |
| Consultas ao banco | Diferenças de `pg_stat_statements` filtradas pelo usuário `tcc_app` |
| Acertos, faltas e fallback das páginas | Contadores Micrometer da API; diferenças entre as coletas de início e fim |
| Memória e expulsões Redis | `INFO memory` e diferenças de `INFO stats` |

Hits/misses internos Redis incluem buscas auxiliares de geração e não medem diretamente páginas atendidas pela aplicação. Registre-os separadamente; calcule o acerto lógico como `hit / (hit + miss + fallback)`, indicando também a proporção de fallback separadamente. Uma falta lógica pode terminar em erro HTTP, por isso preserve as duas medidas.

A API fornece somente `health` e `metrics` na porta administrativa 8081, publicada no loopback da VM. Não exponha essa porta para o gerador ou a rede de usuários. O coletor PostgreSQL usa uma role de monitoramento, sem permissões de escrita nas tabelas de negócio.

Mantenha os relógios sincronizados e registre desvios observados. Os contadores devem ser capturados com a carga quiescente antes da medição e após sua drenagem; o coletor amostra recursos periodicamente, por padrão a cada 5 s. Essa resolução não permite atribuir amostras ao milissegundo. Preserve margens sem carga e os horários reais; se houver ausência de amostras de fronteira ou reinício/reset de contadores, invalide a coleta e repita a execução.

Ao resumir a coleta com `monitoring/resumir.py`, forneça `--measurement-summary` com o resumo k6 da medição para recortar os 300 s. Sem esse argumento, o resultado tem escopo `collection` e inclui a coleta inteira; não o use como resultado da janela experimental. Com a janela, o escopo identifica recursos recortados e contadores delimitados por amostras anteriores/posteriores à carga.

Não zere estatísticas globais PostgreSQL durante a campanha. Os deltas permitem comparar consultas da API sem contabilizar o próprio monitoramento; total de consultas SQL e quantidade de leituras HTTP são grandezas distintas.

## Consolidação

Consolide por perfil, concorrência, modo e tipo de operação. Calcule média, mediana e desvio-padrão dos indicadores das cinco execuções, preserve os valores individuais e compare cada par com a respectiva referência sem cache. Calcule a variação percentual somente com denominador válido e explicite a direção de melhoria de cada métrica.

p95 e p99 consolidados a partir dos percentis individuais são resumos das execuções, não percentis de todas as requisições reunidas. Não elimine falhas ou execuções incompletas silenciosamente. Dados ausentes, reinícios, erros de preparação e quebras do protocolo tornam a execução inválida e devem permanecer registrados.

Antes de iniciar a campanha, registre commit, digests, versões efetivas, recursos, tamanhos da base e índices, pool, paginação, localidade, TTL, timeout, semente e ordem. Consulte [VERSIONS.md](../VERSIONS.md), [registro das VMs](../infra/DEPLOYMENT.md) e [ajustes do texto](AJUSTES_TEXTO_TCC.md).
