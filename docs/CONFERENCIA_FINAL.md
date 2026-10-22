# Conferência final — 22/10/2026

Registro anterior à preparação solicitada nesta data. O estado posterior de disco, dados, automação e piloto está em [PREPARACAO_E_PILOTO.md](PREPARACAO_E_PILOTO.md).

O método do PDF está coerente com a API e com a matriz experimental. A rede e os serviços passaram na verificação após a inicialização de hoje. A campanha ainda depende da preparação de dados, espaço, gerador e automação; esta conferência não produziu resultados de desempenho.

PDF consultado: `/home/rhyanorben/Downloads/TCC.pdf`, 11 páginas, exportado em 22/10/2026. SHA-256: `cda4eb565a692fe78eb6d594665cf4492504b58a6bc55865dfc8545016554908`.

## Ambiente conferido

| Item | Confirmação |
| --- | --- |
| VMs | App 2 vCPU/4 GiB; PostgreSQL 2 vCPU/4 GiB; Redis 1 vCPU/2 GiB; carga 4 vCPU/4 GiB; Ubuntu 24.04.5 LTS nas quatro |
| Virtualização | KVM nas três VMs de serviço; VMware na tcc-load; libvirt 10.0.0 e QEMU 8.2.2 no computador 1 |
| Serviços | Java 21.0.12.1, PostgreSQL 17.11, Redis 7.4.11; Docker 29.9.1 e Compose 5.6.0 nas três VMs de serviço |
| Rede após inicialização | Host iniciado às 08h18, VMs de serviço às 08h21 e tcc-load às 08h22, em 22/10, horário de Brasília. Bridge, driver r8169, segunda NIC, publicações e dados permaneceram disponíveis |
| HTTP pela Ethernet | Duas consultas GET da tcc-load retornaram 200 e três pedidos da empresa 1; rota pela ens37, origem 10.20.20.40 |
| Cache | Após essas leituras: um acerto, uma falta e nenhum desvio por erro; TTL 60 s, timeout 200 ms, limite 1 GiB, allkeys-lru e gravação em disco desativada |
| Isolamento | Portas 5432, 6379 e 8081 recusadas em 10.20.20.10; bancos publicados apenas nos IPs privados |
| Relógios | NTPSynchronized=yes nas quatro VMs; desvios NTP reportados entre aproximadamente −74 e +49 ms. Conferir novamente antes dos ensaios |
| Coleta | Uma amostra real por serviço funcionou: recursos Docker, contadores da API, estatísticas SQL via tcc_monitor e INFO Redis. Isso não valida ainda a coleta contínua nem sua coordenação com a janela experimental |
| Base atual | Duas empresas, dois clientes, seis pedidos e 18 itens; a base de 8.500.100 registros ainda não existe |

As configurações persistiram numa inicialização posterior à configuração de 21/10. Não foi provocado outro reinício durante a conferência. Não houve migração, instalação, carga de dados, restauração, limpeza ou alteração de serviços nesta etapa.

## Preparação ainda necessária

1. **Disco:** computador 1 com cerca de 36 GiB livres e 93% de ocupação. PostgreSQL com cerca de 9,7 GiB livres no volume atual; o disco virtual tem 40 GiB e o grupo LVM possui aproximadamente 19 GiB ainda não alocados. Planejar o volume e o local do backup, então medir crescimento de dados, índices e arquivos de transação numa carga gradual. Esses valores não comprovam que a base completa ficará sem espaço nem autorizam carregá-la sem margem.
2. **Gerador:** k6 nativo 2.3.0 instalado, mas Docker ausente na tcc-load. O executor versionado exige Docker com a imagem k6 1.6.0 fixada por digest. Preparar essa execução para manter a referência do documento; não foi alterado k6 nesta conferência.
3. **Automação:** implementar restauração da base de referência, troca de modo, limpeza Redis, verificações e início/fim dos coletores. Hoje há contratos, não os executáveis específicos das VMs. O backup anterior à API não substitui a base experimental nem um teste de restauração.
4. **Dados e piloto:** carregar e conferir a base, exportar IDs reais, validar planos SQL e restauração, depois executar o piloto nos dois modos. A conferência das funções de coleta não substitui a validação contínua dos arquivos e das fronteiras de medição.

## Trocas no PDF

### Página 5 — virtualização

Substituir o parágrafo iniciado por “As quatro máquinas virtuais serão criadas por meio de KVM/QEMU com libvirt.” por:

> No primeiro computador, as três máquinas virtuais serão executadas em KVM/QEMU com libvirt e hospedarão a aplicação Spring Boot, o PostgreSQL e o Redis, interligados por uma rede virtual privada. No segundo computador, a VM geradora de carga será executada em VMware e acessará a aplicação pela rede Ethernet de 1 Gbit/s.

### Página 9 — Quadro 2

| Texto atual | Substituição |
| --- | --- |
| Acertos e falhas | Acertos e faltas |
| Desvios por falha | Desvios ao banco por falha |

Uma falta de página em cache não equivale a uma falha do Redis. A largura atual do quadro comporta os textos; o quadro já está legível e dentro da página.

### Página 8 — quantidade de execuções

Para evitar interpretar que existem 200 pares, substituir somente “totalizando 200 execuções pareadas” por “totalizando 200 execuções, organizadas em 100 pares”.

### Página 7 — Figura 2

No bloco da escrita, substituir “Invalida chave no Redis” por “Renova versão da empresa”. Isso representa o mecanismo implementado; as páginas antigas expiram sem exclusão individual imediata.

### Página 8 — ritmo das requisições

Na primeira frase do parágrafo sobre as 25 empresas, substituir:

> Os usuários virtuais serão distribuídos igualmente entre as mesmas 25 empresas em todos os níveis de concorrência; as demais permanecerão apenas na base.

por:

> Os usuários virtuais enviarão requisições sequenciais, sem pausa programada, e serão distribuídos igualmente entre as mesmas 25 empresas; as demais permanecerão apenas na base.

O código utiliza usuários concorrentes constantes, sem espera deliberada entre operações durante a carga. A alteração registra essa condição sem criar outro parágrafo.

## Observações de apresentação e fechamento

- Manter k6 1.6.0 no Quadro 1 se for utilizado o executor versionado; preparar o ambiente para essa referência. Padronizar a grafia “k6” no lugar de “K6”.
- Na página 4, mover a legenda da Figura 1 para junto da imagem, na página 5, sem inserir texto novo.
- Resumo, palavras-chave, resultados e considerações finais ainda contêm texto do modelo. Finalizá-los depois da campanha, sem antecipar resultados.
- Esta conferência trata do alinhamento experimental e da apresentação das páginas metodológicas; não revalida os estudos citados nem certifica todas as regras de normalização bibliográfica.

Não é necessário reduzir empresas, registros, cenários ou repetições nesta etapa. Primeiro adequar o ambiente ao método já definido e validar o piloto.
