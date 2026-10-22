# Preparação e piloto — 22/10/2026

A base completa e a restauração foram validadas no banco dedicado `tcc_experimento`. A API usa a mesma imagem nos dois modos; o banco `tcc` anterior foi preservado. A campanha de 200 execuções ainda não foi iniciada.

## Dados e espaço

| Item | Estado conferido |
| --- | --- |
| Base `base-v1` | 100 empresas, 500.000 clientes, 2.000.000 pedidos e 6.000.000 itens |
| Conteúdo | 5.000 clientes, 20.000 pedidos e três itens por pedido em cada empresa; totais e vínculos validados na geração |
| Volume PostgreSQL | Ampliado de 19 para 32 GiB dentro do disco virtual existente de 40 GiB; aproximadamente 6 GiB permanecem livres no grupo LVM |
| Tabelas e índices | 677,6 MiB de dados e 474,0 MiB de índices nas quatro tabelas; banco completo com aproximadamente 1,13 GiB |
| Espaço após preparação | 19,7 GiB livres na VM PostgreSQL; 26,6 GiB livres no notebook |
| Margens operacionais | Manter pelo menos 12 GiB livres no notebook e 5 GiB na VM PostgreSQL; conferir antes da campanha e acompanhar sua evolução |

Os índices da migração V1 foram mantidos: chaves primárias, unicidade por empresa e índices para paginação, cliente e itens do pedido. O plano da primeira página usa o índice de ordenação; a página 800 processa mais linhas e ordena o resultado. Na conferência isolada, essas consultas levaram aproximadamente 0,2 ms e 65,6 ms; a contagem usou somente o índice e levou 2,6 ms. Não alterar índices entre modos ou repetições. Os planos são verificações administrativas fora da medição HTTP.

O orçamento conservador da campanha considera a imagem virtual de até 40 GiB, aproximadamente 13,4 GiB já alocados, 12 GiB de reserva no notebook e 1 GiB para resultados. A meta é dispor de 40 GiB livres no host antes de uma campanha longa sem acompanhamento; faltam cerca de 14 GiB para essa meta. A base atual ocupa muito menos, mas o espaço livre dentro da VM não garante espaço físico no notebook. Não foram removidos arquivos pessoais.

## Referência e recuperação

O backup de referência tem 39,3 MiB (41.181.001 bytes). Foi restaurado em `tcc_validacao_restore`, com conferência das quatro contagens e dos dois milhões de pedidos inicialmente `ABERTO`; somente essa cópia temporária foi removida após a validação. Cada caso do piloto também restaurou a referência antes do aquecimento.

A referência fica na VM PostgreSQL e possui uma segunda cópia no computador 2, ambas conferidas pelo SHA-256 `84af910f36b945af6080fc8bb8df2a39835dfa388cd81689ab40483a64baa58f`. O backup do banco anterior foi preservado separadamente. Caminhos, proteções e reversão estão em [infra/experiment/README.md](../infra/experiment/README.md). Não criar um backup integral por execução; preservar a referência e exportar os resultados de cada ensaio.

## Geradora e automação

A tcc-load, com 4 vCPU e 4 GiB, recebeu Docker e a imagem k6 1.6.0 fixada pelo digest de [VERSIONS.md](../VERSIONS.md). O binário nativo 2.3.0 permanece instalado, mas não é usado pelo executor. PostgreSQL, Redis e gerenciamento HTTP continuam restritos à rede privada ou ao loopback.

Os hooks reais coordenam restauração, seleção de modo, limpeza Redis, conferência do manifesto e três coletores. O operador autentica sessões SSH/sudo temporárias; não foram mantidas novas chaves nem instaladas permissões sudo sem senha. A restauração recusa outro banco, identificação experimental ausente, hash divergente, conexões abertas da API ou espaço abaixo do limite.

O exportador do manifesto foi ajustado para calcular as contagens uma vez por empresa. O arquivo final manteve o mesmo conteúdo e hash; a consulta da API permanece igual. Uma tentativa interrompida nessa preparação foi preservada como inválida, sem iniciar a carga.

## Piloto

Foi usado um par 90/10, com 25 usuários, as mesmas 25 empresas, dois minutos de aquecimento e cinco minutos de medição em cada modo. Plano com semente `20261032`, par `90-10-vu025-r3`, semente da carga `236a57e26cdff673`. A repetição identificada como `r3` é o primeiro par sorteado no plano; não representa três pilotos.

| Cache | Leituras | Escritas | Req./s | p95 da leitura | Erros |
| --- | ---: | ---: | ---: | ---: | ---: |
| Desligado | 46.489 | 5.168 | 172,19 | 318,85 ms | 0 |
| Ligado | 47.783 | 5.300 | 176,94 | 308,73 ms | 0 |

No modo com cache foram registrados 1.289 acertos, 46.494 faltas, 5.300 invalidações e nenhum desvio ao banco por falha do cache. O acerto lógico foi de 2,7%. O PostgreSQL consumiu, em média, cerca de 197% de CPU Docker nos dois modos, próximo da capacidade das duas vCPUs; a paginação profunda deve ser considerada na interpretação. Isso não autoriza mudar índices, recursos ou localidade entre os casos da campanha.

A geradora apresentou, nas amostras da medição, até 45,4% de um núcleo de CPU e 106,2 MiB de memória do contêiner k6, sem indicação de sobrecarga neste nível de concorrência. Os arquivos brutos e os resumos dos três coletores cobrem as fronteiras da medição. O aquecimento foi excluído. Este único par valida o procedimento e não sustenta conclusões finais sobre o benefício do cache; são necessárias as cinco repetições de cada cenário.

Evidências locais em `results/piloto-20261022/`, ignoradas pelo Git: plano, manifesto, recibos dos hooks, resumos k6, coletas originais, planos SQL, tamanhos e conferência da restauração. Os testes executados nesta preparação aprovaram 35 casos de monitoramento, nove de carga e dez das proteções/sessões manuais. Código Java e imagem da API não foram alterados.

## Estado final e próxima etapa

A referência foi restaurada após o piloto. A API permanece com cache ligado em `tcc_experimento`; o GET pela tcc-load retornou 200, com 20 pedidos da empresa 1 e total de 20.000 pedidos. As sessões temporárias e os coletores foram encerrados. O método definido no documento foi mantido; esta preparação não exige nova alteração no PDF.

Antes da campanha, atender ao orçamento de espaço ou executar blocos acompanhados com verificação de disco entre eles, versionar as alterações revisadas, registrar o commit do executor, reconferir relógios, reservar a janela de execução e abrir as sessões manuais com duração suficiente. A matriz mantém 200 execuções em 100 pares: são pelo menos 23h20 de carga, além de restaurações e preparação. Acompanhar também o consumo do gerador nos níveis maiores. A [execução documentada](../infra/experiment/README.md) usa `--limite 2` para o piloto; a campanha completa deve ser iniciada em outro diretório e mediante decisão própria.
