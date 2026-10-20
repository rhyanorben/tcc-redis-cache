# Trocas no texto do TCC

Referência: PDF recebido em 16/10/2026. Os trechos citados servem para localizar as substituições e preservam a redação original, com espaços e quebras de linha normalizados. Copie somente o conteúdo indicado em **Por** e os quadros propostos. A numeração de páginas corresponde ao PDF original, que permanece intacto.

A revisão mantém um parágrafo por substituição textual, aproveita o Quadro 1 existente e apresenta as escolhas do experimento sem detalhes de configuração. As redações descrevem o procedimento futuro, não resultados já obtidos.

## 1. Páginas 5–6 — versões no quadro existente

**Primeiro, substitua o Quadro 1 da página 5 pelo quadro abaixo.** Ele reúne as versões acima do parágrafo e dispensa um quadro adicional. As configurações são previstas para a campanha; a VM de carga ainda depende de validação.

**Quadro 1: Configurações das máquinas virtuais e versões previstas**

| Função | vCPU | RAM (GiB) | Tecnologias e versões |
| --- | --- | --- | --- |
| Aplicação | 2 | 4 | Java 21; Spring Boot 3.5.16 |
| Banco de dados | 2 | 4 | PostgreSQL 17.11 |
| *Cache* | 1 | 2 | Redis 7.4.11 |
| Geração de carga | 4 | 4 | k6 1.6.0 |

Fonte: O Autor (2026).

Nota: Ubuntu Server 24.04 LTS em todas as VMs; Docker Engine 29.9.1 e Docker Compose 5.6.0 nas VMs dos serviços.

**Depois, na página 6, trocar este trecho:**

> Durante os experimentos serão mantidas fixas as versões das tecnologias empregadas. Serão utilizados Java [versão], Spring Boot [versão], PostgreSQL [versão], Redis [versão], Docker [versão] e k6 [versão].

**Por:**

As versões das tecnologias apresentadas no Quadro 1 serão mantidas fixas durante os experimentos. A mesma versão da aplicação será utilizada com e sem *cache*.

## 2. Página 6 — configuração Redis

**Trocar este trecho:**

> O Redis será configurado exclusivamente como camada de cache, sem utilização de mecanismos de persistência. A memória destinada ao armazenamento das entradas será limitada a 1 GB, sendo adotada a política de remoção allkeys-lru, que prioriza a remoção das entradas menos recentemente utilizadas quando o limite estabelecido é atingido. As entradas não possuirão tempo de expiração automático, de modo que a consistência entre o cache e o PostgreSQL será mantida por meio da invalidação das chaves correspondentes após operações de escrita.

**Por:**

O Redis será utilizado exclusivamente como *cache*, sem gravação dos dados em disco, com limite de memória de 1 GiB e remoção das entradas menos recentemente utilizadas quando esse limite for atingido. As páginas expirarão 60 segundos após a gravação, sem renovação pelas leituras. A confirmação de uma escrita no PostgreSQL invalidará todas as páginas da empresa. Esses parâmetros permanecerão fixos nos testes com *cache*.

## 3. Página 6 — composição e volume da base

**Trocar este trecho:**

> A base experimental representará uma aplicação SaaS de gestão empresarial e utilizará tabelas compartilhadas entre diferentes inquilinos, identificados pelo atributo tenant_id. Será composta por 100 inquilinos, contendo aproximadamente 5.000 clientes, 2.000 produtos, 20.000 pedidos e 60.000 itens de pedido por inquilino, resultando em aproximadamente 8,7 milhões de registros. A proporção entre pedidos e itens corresponderá, em média, a três produtos por pedido.

**Por:**

A base experimental utilizará tabelas compartilhadas com as entidades empresa, cliente, pedido e item de pedido. Serão 100 empresas, cada uma com 5.000 clientes, 20.000 pedidos e 60.000 itens, somando 8.500.100 registros na base. Cada pedido terá três itens, com dados e datas determinísticos. As leituras retornarão resumos paginados de pedidos e dados do cliente, sem carregar os itens.

## 4. Página 7 — estratégia de cache e consistência

**Trocar este trecho:**

> Será utilizada a estratégia cache-aside, na qual os dados recuperados do PostgreSQL serão posteriormente armazenados no Redis. As chaves de cache incluirão o identificador do inquilino, evitando o compartilhamento indevido de informações entre diferentes inquilinos. Nas operações de escrita, os dados serão atualizados no PostgreSQL e as respectivas entradas armazenadas no Redis serão invalidadas. A manutenção da consistência constitui uma característica relevante em sistemas de cache, uma vez que alterações na fonte principal podem tornar cópias armazenadas em memória desatualizadas (ZHENG et al., 2022). A Figura 2 apresenta o fluxo empregado nas operações de leitura e escrita quando a camada de cache estiver habilitada.

**Por:**

Será utilizada a estratégia *cache-aside*: as páginas de 20 pedidos serão procuradas no Redis e, quando ausentes, consultadas no PostgreSQL e armazenadas no *cache*. A ordenação será decrescente por data de criação e identificador. As chaves distinguirão empresa e parâmetros da consulta. Após a confirmação da escrita, será alterada a versão do *cache* da empresa, invalidando todas as suas páginas; as antigas ficarão inacessíveis até sua remoção ou expiração. Falhas do *cache* direcionarão a leitura ao banco; entre a escrita e a invalidação, podem ocorrer leituras desatualizadas (Zheng *et al.*, 2022). A Figura 2 apresenta esse fluxo.

## 5. Página 8 — empresas ativas, localidade e escrita

**Trocar este trecho:**

> Durante os testes, cada usuário virtual será associado a um dos inquilinos cadastrados na aplicação e realizará operações sobre os registros pertencentes a esse inquilino. Para representar a repetição de acessos observada em aplicações reais, alguns registros serão consultados com maior frequência que outros. Dessa forma, aproximadamente 80% das operações de leitura serão realizadas sobre 20% dos registros de cada inquilino, enquanto os demais acessos serão distribuídos entre os outros registros. A mesma distribuição de acessos, os mesmos registros de referência e os mesmos parâmetros de carga serão utilizados nos testes com e sem Redis, permitindo que as duas configurações sejam avaliadas sob condições equivalentes.

**Por:**

Os usuários virtuais serão distribuídos igualmente entre as mesmas 25 empresas em todos os níveis de concorrência; as demais permanecerão apenas na base. Cerca de 80% das leituras consultarão um conjunto fixo de 20% das páginas de cada empresa ativa, e as restantes acessarão as outras páginas. As escritas alternarão o estado de um pedido exclusivo de cada usuário, produzindo alterações reais sem inserir ou excluir pedidos. Empresas, páginas, pedidos de escrita e parâmetros serão preservados entre os modos comparados.

## 6. Página 8 — repetições e pares

**Trocar este trecho:**

> Cada combinação será executada tanto na configuração sem cache quanto na configuração com Redis e será repetida cinco vezes, resultando em 200 execuções experimentais.

**Por:**

Cada combinação será executada com e sem *cache*, em cinco repetições, totalizando 200 execuções pareadas. Cada par usará a mesma base, parâmetros e semente de seleção, com a ordem dos modos aleatorizada. A duração fixa permite quantidades diferentes de requisições entre os modos.

## 7. Página 8 — restauração e condição inicial

**Trocar este trecho:**

> Antes de cada execução, o estado lógico da base será restaurado para uma condição de referência previamente definida, evitando que alterações produzidas pelas operações de escrita em execuções anteriores influenciem os testes subsequentes.

**Por:**

Antes de cada execução, será aguardada a conclusão das requisições anteriores. O banco experimental será restaurado da mesma cópia de referência, e o Redis dedicado será esvaziado, inclusive antes dos testes sem *cache*. Nenhuma outra aplicação acessará esses serviços durante a campanha.

## 8. Página 8 — aquecimento e medição

**Trocar este trecho:**

> Antes de cada execução será realizado um período de aquecimento de dois minutos, não considerado na análise, seguido de cinco minutos destinados à coleta das métricas. Nos testes com Redis, o conteúdo do cache será removido antes do período de aquecimento, permitindo seu preenchimento inicial antes da etapa de medição e garantindo condições iniciais equivalentes entre as repetições.

**Por:**

Cada execução terá dois minutos de aquecimento somente com leituras, excluídos da análise, seguidos de cinco minutos de medição com o perfil correspondente. Após cada etapa, será aguardada a conclusão das requisições em andamento. O *cache* começará vazio antes do aquecimento e manterá a expiração de 60 segundos durante ambas as etapas.

## 9. Páginas 8–9 — métricas e delimitação da coleta

**Trocar este trecho:**

> As principais métricas coletadas serão tempo de resposta, percentis p95 e p99, vazão de requisições, taxa de erros e utilização de CPU e memória. Também serão registradas estatísticas do PostgreSQL e do Redis, incluindo quantidade de consultas direcionadas ao banco, utilização de memória do cache, acertos e falhas de consulta. Estudos de desempenho de sistemas distribuídos utilizam métricas como tempo de resposta e utilização de CPU para comparar diferentes configurações sob carga (NISWAR et al., 2024).

**Por:**

As métricas e os instrumentos constam no Quadro 2, com as medidas das requisições separadas por leitura e escrita. A coleta excluirá o aquecimento, utilizará relógios sincronizados e amostrará recursos a cada cinco segundos. Os contadores serão comparados antes da medição e após a conclusão das requisições. A taxa de acerto será a razão entre acertos e a soma de acertos, faltas e desvios ao banco por falha do *cache*. Estatísticas internas do Redis serão auxiliares. Estudos de desempenho utilizam tempo de resposta e CPU para comparar configurações sob carga (Niswar *et al.*, 2024).

## 10. Página 9 — consolidação

**Trocar este trecho:**

> Os resultados das cinco repetições serão consolidados para cada cenário, permitindo comparar as configurações com e sem Redis em condições equivalentes. Serão utilizadas medidas como média, mediana, desvio-padrão e variação percentual, além de gráficos relacionando o aumento da concorrência às métricas coletadas.

**Por:**

As cinco repetições válidas serão consolidadas por perfil, concorrência, modo e operação, com média, mediana, desvio-padrão e variação percentual entre os modos de cada par. Os percentis serão resumidos por execução, sem tratá-los como percentis de todas as requisições reunidas. Serão apresentados gráficos de concorrência e métricas. Execuções incompletas serão registradas e repetidas.

## 11. Página 9 — Quadro 2 completo

**Trocar o Quadro 2 atual:**

| Métrica | Origem |
| --- | --- |
| Tempo de resposta, p95 e p99 | k6 |
| Vazão de Requisições | k6 |
| Taxa de erros | k6 |
| CPU e memória de aplicação | Docker |
| CPU e memória do PostgreSQL | Docker |
| CPU e memória do Redis | Docker |
| Quantidade de consultas ao PostgreSQL | Estatísticas do PostgreSQL (pg_stat_statements) |
| Cache hits e cache misses | Estatísticas do Redis (INFO stats) |
| Memória ocupada pelo cache | Estatísticas do Redis (INFO memory) |

Fonte: O Autor (2026)

**Por:**

**Quadro 2: Métricas e instrumentos de coleta**

| Grupo | Métrica | Coleta |
| --- | --- | --- |
| Requisições | Tempo de resposta | k6 |
| Requisições | Percentis p95 e p99 | k6 |
| Requisições | Vazão | k6 |
| Requisições | Taxa de erros | k6 |
| Aplicação | CPU e memória | Docker |
| PostgreSQL | CPU e memória | Docker |
| Redis | CPU e memória | Docker |
| PostgreSQL | Comandos SQL da aplicação | Estatísticas do banco |
| *Cache* | Acertos e faltas | Aplicação |
| *Cache* | Desvios por falha | Aplicação |
| *Cache* | Memória utilizada | Redis |
| *Cache* | Remoções por falta de memória | Redis |

Fonte: O Autor (2026).

## Ajustes de apresentação

- Na Tabela 1 da página 8, trocar **Perifl** por **Perfil**; manter os cenários.
- Na Figura 2 da página 7, trocar **Invalida chave no Redis** por **Atualiza a versão do *cache* da empresa**.
- Os trechos novos já apresentam *cache*, *cache-aside* e *et al.* em itálico. Nomes como Redis, Java, Spring Boot, PostgreSQL, Docker e k6, além de siglas e unidades, permanecem sem esse destaque.
- Nas citações propostas, usar (Zheng *et al.*, 2022) e (Niswar *et al.*, 2024), com sobrenomes em maiúsculas e minúsculas. Os blocos antigos preservam a forma do PDF apenas para localização.

Os detalhes operacionais permanecem em [EXPERIMENTO.md](EXPERIMENTO.md), sem precisar ampliá-los no artigo. A formatação foi conferida com a ABNT NBR 14724:2024, versão corrigida em 2025, e as orientações de citação da ABNT NBR 10520:2023: [norma de apresentação](https://vigilanciasanitaria.prefeitura.rio/wp-content/uploads/sites/84/2025/10/ABNT-NBR-14724-2025-informacao-e-documentacao-trabalho-academico.pdf), [orientação institucional sobre citações](https://periodicos.ufsc.br/index.php/workingpapers/about/submissions) e [itálico de estrangeirismos](https://revistas.usp.br/flp/pt_BR/about/submissions). Estas notas não integram o texto a copiar para o artigo.
