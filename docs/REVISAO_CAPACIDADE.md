# Revisão de capacidade e campanha 2

A campanha original parou no cenário 90/10, com 500 usuários e cache ligado. A API esgotou as dez conexões PostgreSQL e uma escrita excedeu os 5 s de espera: o k6 abortou aos 104 dos 300 s previstos. O banco chegou próximo da capacidade dos seus dois processadores. O [diagnóstico original](../results/campanha-20261023/diagnostico-bloco-02.md) e os arquivos da campanha permanecem preservados.

A implementação abria transação antes de consultar Redis, mantendo esse recurso também no caminho de acerto e impedindo a aplicação da isolação definida na consulta interna. A regra anterior abortava diante de qualquer erro de escrita; não distinguia uma recusa anterior à execução de uma resposta perdida após possível commit.

## Correção

| Ponto | Comportamento revisado |
| --- | --- |
| Acerto no cache | Retorno sem transação PostgreSQL e sem ocupar admissão ao banco |
| Consulta ao banco | Transação própria `REPEATABLE_READ`, somente no miss/fallback |
| Admissão | Fila justa, até dez operações simultâneas e espera de 5 s antes da transação |
| Saturação da admissão | HTTP 503 específico, com garantia de operação não aplicada |
| Escrita incerta | Aborto mantido para timeout, 500, 503 genérico ou contrato inválido |
| Monitoramento após aborto | Encerramento separado da validação do resumo; dados brutos preservados |
| Resultados | Tentativas, sucessos e recusas separados, com vazão e latências de sucesso próprias |

A admissão usa o tamanho e a espera do pool existente. Não foram reduzidos usuários nem ampliados pool, timeout, CPU ou memória para contornar a saturação. O mesmo artefato e a mesma política são usados com cache desligado e ligado. O [protocolo 2](EXPERIMENTO.md) registra essas condições.

Uma recusa só é reconhecida com HTTP 503 e os três campos exatos: `type=urn:tcc:problem:database-capacity`, `code=DATABASE_CAPACITY_EXCEEDED`, `operationApplied=false`. Ela permanece na taxa de erros. A requisição seguinte segue o perfil; a alternância do status de escrita avança somente após sucesso. Não há retentativa automática para esconder recusas.

Essa proteção não aumenta a capacidade física nem garante ausência de erros com 500 usuários. Medições com saturação podem ser válidas; ganho de desempenho precisa considerar sucesso, erro, latência e recursos conjuntamente. Falhas incertas continuam interrompendo. Testes locais e uma leitura funcional após a implantação não substituem observação sob carga.

## Reinício e execução

A campanha revisada usa `/home/rhyan/tcc-runner-v2/results/campanha-20261024-v2` na geradora e `results/campanha-20261024-v2` no notebook. Mantém base, índices, plano, sementes e matriz; repete todas as medições com a API revisada. O bloco 1 anterior permanece registro válido da configuração original, fora da nova consolidação.

A revisão foi implantada e a conferência sem carga passou. Não foram iniciados ensaios ou piloto pelo chat. Primeiro execute o piloto manual no notebook:

```sh
cd /home/rhyanorben/Documentos/RhyanPessoal/tcc-redis-cache
python3 scripts/executar_bloco.py --piloto
```

O piloto repete as duas execuções do par 90/10, com 500 usuários, repetição 4, onde houve a falha original. Usa a mesma base, semente e tempos completos; estime 16–22 minutos e reserve 25. Salva em `/home/rhyan/tcc-runner-v2/results/piloto-capacidade-v2/exports/piloto-capacidade.zip`, com cópia para `results/campanha-20261024-v2/piloto-capacidade.zip`. Cada tentativa registra `eligible_for_campaign=false` e `excluded_from_campaign=true` em `pilot.json`; a consolidação seleciona apenas pares confirmados em `blocks/` da campanha, sem alcançar a pasta do piloto.

Apresente esse ZIP para validação; depois execute `python3 scripts/executar_bloco.py --bloco 1` e confira seu pacote antes de continuar com `--blocos 2-5`. O bloco deve levar 1h20–1h45; quatro blocos, 5h20–7h, com reserva de 8h. A sessão é `tcc-campanha-v2`. Resultados e retomada estão no [guia de execução](CAMPANHA_EM_BLOCOS.md).

## Troca no texto do TCC

O PDF não foi editado. Na seção de métricas, localize o parágrafo iniciado por **“As métricas e os instrumentos constam no Quadro 2”**, proposto anteriormente em [AJUSTES_TEXTO_TCC.md](AJUSTES_TEXTO_TCC.md), e substitua-o por este único parágrafo:

As métricas do Quadro 2 separarão leituras e escritas, com tentativas, sucessos e recusas. A vazão e as latências das operações bem-sucedidas serão apresentadas separadamente. A coleta excluirá o aquecimento, com relógios sincronizados, amostras a cada cinco segundos e contadores antes da medição e após a conclusão das requisições. Nos dois modos, até dez operações acessarão o banco simultaneamente, com espera de cinco segundos. Recusas anteriores à transação contarão como erros; falhas de escrita com resultado incerto interromperão a execução. O acerto do *cache* será a razão entre acertos e a soma de acertos, faltas e desvios por falha; estatísticas internas do Redis serão auxiliares (Niswar *et al.*, 2024).

Mantenha os cenários, tempos, recursos e número de repetições dos quadros. No Quadro 2, a vazão passa a distinguir tentativas e sucessos, e a taxa de erros inclui as recusas. Não é necessário acrescentar nomes de classes, códigos HTTP ou termos de configuração ao artigo.
