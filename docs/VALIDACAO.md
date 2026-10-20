# Validação do alinhamento experimental

## Projeto

As alterações estão integradas no repositório `/home/rhyanorben/Documentos/RhyanPessoal/tcc-redis-cache`. Nenhum commit foi criado.

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

O gerador prepara SQL com três itens por pedido e valida contagens e totais antes do commit. A base completa de 8.500.100 registros não foi carregada.

## Ambiente

Os ajustes aplicados às VMs em 16/10/2026 estão no [registro de implantação](../infra/DEPLOYMENT.md). Em 17/10 as VMs estavam desligadas. A revisão automática de aprovação rejeitou iniciar a VM PostgreSQL, considerando necessária confirmação específica para ligá-la; por isso, a verificação ao vivo dos serviços não foi repetida. A consulta somente leitura ao libvirt em 20/10 confirmou as três VMs desligadas. Não houve nova tentativa de ligá-las nem alteração de seus serviços.

A API, as migrações de negócio, a VM de carga, os executáveis específicos dos hooks e a campanha continuam pendentes de implantação e validação. Os contratos dos hooks estão documentados; não equivalem a backup, restauração, limpeza Redis ou sincronização remota já implementados.

## Texto do TCC

[AJUSTES_TEXTO_TCC.md](AJUSTES_TEXTO_TCC.md) contém 11 substituições completas, com trecho antigo e redação nova, além dos ajustes na tabela e na figura. O PDF original permanece intacto.
