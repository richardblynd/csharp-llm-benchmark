# Plano para avaliar adição de features em projetos C# existentes

Proposta de implementação, baseada no código do repositório em 13/10/2026.
Este documento registra o desenho completo recomendado. A implementação atual
inclui seis desafios pontuados: pilha, catálogo HTTP, notificações, reservas,
inventário SQLite e outbox. São dois por dificuldade, somando 120 pontos.
Também implementa
`--suite evolution`, snapshots de múltiplos
arquivos, `--suite all` para executar as duas modalidades, testes ocultos
separados e pontuação por feature/preservação nos dois generators.
A validação real em Docker confirmou starter=0, referência=100 e
regressão deliberada=80 para a pilha. O primeiro build em WSL foi corrigido
isolando o estado .NET/NuGet dentro do container (ADR-0004).
Nas reservas, a validação confirmou starter=0, referência=100,
quebra de atomicidade=65 e quebra de contrato antigo=85,71.
A descoberta própria de temperatura (quatro desafios independentes), as campanhas
retomáveis e o relatório com duas modalidades e combinado foram implementados em
15/10/2026 (ADR-0008). Os testes do fluxo usam generators simulados; a validação
dos desafios de descoberta usa o avaliador Docker real, sem sessões de LLM.
O próximo piloto real deve executar a campanha completa com discovery habilitado.
As etapas abaixo preservam o desenho e as propostas de expansão. As execuções
históricas com somente pilha e
reservas tinham 30 pontos e representam um catálogo menor.

O benchmark deve produzir duas medidas independentes: construção do zero
(`greenfield`) e adição de features (`evolution`). Ambas usam PI e OpenCode,
calibração de velocidade, descoberta de temperatura e avaliação por testes
ocultos. O score combinado atribui o mesmo peso às duas modalidades.

1. **Criar desafios novos, reaproveitando domínios e testes de regressão.**

   Os desafios atuais continuam medindo construção do zero. Para a modalidade
   nova, entregar uma implementação funcional, congelada e revisada, acompanhada
   de um pedido de mudança. Não basta disponibilizar os stubs atuais, nem pedir
   que a LLM complete métodos vazios: isso continuaria medindo implementação
   inicial.

   Reaproveitar alguns domínios existentes reduz o trabalho de autoria e permite
   reutilizar testes atuais como regressão. Os testes da feature e das suas
   interações com o comportamento existente precisam ser novos. Não converter
   automaticamente todos os desafios: exercícios como soma de listas oferecem
   pouco contexto para avaliar manutenção.

   O projeto inicial deve conter código distribuído em arquivos coerentes,
   namespaces, interfaces e dependências quando fizerem sentido, além de um
   README com instruções de build e descrição do comportamento existente.
   A LLM precisa localizar onde alterar o código e integrar a mudança aos
   consumidores reais, não apenas implementar uma classe sem uso.

   O pedido deve especificar comportamento observável, casos de erro e
   compatibilidade exigida. Não revelar o algoritmo ou enumerar cada arquivo
   que precisa ser alterado. As regras do projeto devem ser explícitas; testes
   ocultos não podem exigir requisitos que não constem do contrato público.

   Cada desafio começa de uma cópia nova do mesmo projeto inicial. Não usar a
   saída de uma execução da LLM como ponto de partida de outra: erros acumulados
   tornariam a dificuldade dependente das execuções anteriores.

2. **Começar com seis desafios pontuados e quatro desafios de descoberta.**

   | Dificuldade | Projeto inicial | Feature proposta | Regressão principal |
   | --- | --- | --- | --- |
   | Easy | Pilha genérica funcional | `TryPop` e `TryPeek` | LIFO, contagem e exceções dos métodos antigos |
   | Easy | Catálogo HTTP com CRUD funcional | Busca com filtro e ordenação, preservando o contrato sem parâmetros | CRUD, validações e formato das respostas antigas |
   | Medium | Roteador de notificações com canais | Novo envio com fallback entre canais | Envio atual para todos os canais, ordem e canais customizados |
   | Medium | API de reservas funcional | Reagendamento atômico | Conflitos, intervalos adjacentes e preservação da reserva se a mudança falhar |
   | Hard | Inventário SQLite funcional | Reserva e liberação de estoque | Transações, saldo, histórico e gerenciamento da conexão |
   | Hard | Outbox com worker funcional | Backoff e dead-letter configuráveis | Idempotência, cancelamento, concorrência e comportamento padrão atual |

   Esses seis domínios já têm contratos públicos em seus prompts e READMEs,
   projetos iniciais funcionais, referências e testes ocultos separados.
   A dificuldade deve refletir o esforço da alteração, não a classificação do domínio original.
   Na outbox, por exemplo, as novas opções devem conservar o comportamento
   anterior quando não configuradas. No inventário, explicitar a relação entre
   estoque total e reservado, inclusive nas operações antigas.

   Os quatro desafios de descoberta devem ser independentes dos pontuados e
   cobrir coleções, composição/OOP, HTTP e persistência/concorrência. Compartilhar
   padrões de habilidade é adequado; não reutilizar o mesmo pedido de mudança.

   Após validar o pipeline, ampliar a suíte pontuada para doze desafios, quatro
   por dificuldade. Acrescentar variações de cache com expiração, política por
   chave no rate limiter, estratégia de preços e operação em documentos com
   isolamento entre tenants. Congelar a composição e os pesos antes de comparar
   modelos; seis desafios servem como piloto, com cobertura ainda limitada.

3. **Separar modalidade, dificuldade, papel e generator no modelo de tarefas.**

   `generator` continua sendo `pi` ou `opencode`. A modalidade é uma dimensão
   independente. Acrescentar `suite: greenfield|evolution`,
   `role: scored|discovery`, versão da tarefa e metadados explícitos de
   dificuldade. Não inferir dificuldade apenas pelo prefixo do ID.

   Preservar `tasks/easy`, `tasks/medium` e `tasks/hard`. As tarefas novas ficam
   em `tasks/evolution/<difficulty>/<task>/`, com IDs exclusivos, por exemplo
   `evolution-medium-002`. O loader atual enumera todos os diretórios como
   dificuldades; ele precisa passar a carregar raízes conhecidas para não
   tratar `evolution` como uma dificuldade.

   Cada tarefa nova contém `task.yaml`, `prompt.md`, `starter/`,
   `tests/regression/`, `tests/feature/` e `reference/`. `starter/` contém
   apenas o material público; testes e referência não entram no container do
   generator. As soluções em `reference/` existentes podem auxiliar a autoria,
   depois de revisadas e transformadas em projetos apropriados.

   No manifesto, declarar arquivos públicos, padrões de arquivos editáveis,
   projeto de build, comandos de cada suíte de testes, pesos e arquivos
   imutáveis. Usar mappings e listas de strings, compatíveis com o parser YAML
   atual; não exigir listas de objetos ou recursos avançados do YAML.

   Para tarefas antigas, ausência de `suite` significa `greenfield` e o contrato
   de `generated_file` continua válido. Cada suíte informa separadamente sua
   lista de descoberta. A suíte de evolution não deve pular silenciosamente
   a descoberta se seus desafios estiverem ausentes: uma execução oficial
   deve parar com um diagnóstico.

4. **Entregar e avaliar um projeto completo, mantendo um runner compartilhado.**

   Hoje há três restrições relevantes em `benchmark/generation.py`:
   os arquivos iguais a `generated_file` não são copiados para os generators;
   as instruções exigem criar um único arquivo; e o retorno extrai somente esse
   arquivo, rejeitando namespaces. Em `benchmark/runner.py`, a avaliação copia
   o template novamente e aplica somente o conteúdo extraído. Alterações em
   outros arquivos feitas pelo agente não participam da avaliação.

   Introduzir um artefato de entrega no retorno compartilhado de
   `GeneratedSolution`: arquivo único para greenfield ou snapshot do projeto
   para evolution. O avaliador recebe esse artefato, sem depender de detalhes
   do generator. Um módulo pequeno, por exemplo `benchmark/workspace.py`, pode
   concentrar a preparação do projeto, validação dos caminhos, captura da
   entrega e reconstrução da cópia que será avaliada.

   Para evolution, PI e OpenCode recebem o mesmo starter completo e regras de
   alteração equivalentes. Permitir criar, modificar e remover fontes dentro
   dos padrões declarados. Preservar namespaces e convenções do starter; não
   exigir uma classe artificial `Solution` nem um arquivo único. Manter .NET 8
   e as dependências já fornecidas. Na primeira versão, projetos, referências
   de pacotes e arquivos de configuração do build são imutáveis; fontes de
   inicialização como `Program.cs` podem ser editáveis quando a feature exigir.

   Capturar arquivos e remoções em um manifesto, com hashes e um diff entre
   starter e entrega. Ignorar caches, `bin`, `obj`, logs e configuração dos
   generators. Verificar alterações proibidas em arquivos públicos imutáveis;
   apenas ignorá-las permitiria que o build visto pelo agente divergisse da
   entrega avaliada. Rejeitar caminhos fora do projeto e links que escapem dele.

   Depois de encerrar a sessão, montar uma cópia nova e isolada com o starter,
   as alterações permitidas e os arquivos de avaliação controlados pelo runner.
   Não copiar indiscriminadamente todo o workspace do generator. A LLM pode
   criar verificações próprias, mas elas não substituem os testes oficiais.

   Generalizar a configuração de exclusão de fontes de testes: hoje o runner
   escreve `Directory.Build.targets` com uma condição específica para um
   projeto chamado `Solution`. Os projetos novos podem ter outros nomes e
   caminhos; os arquivos de testes nunca devem ser compilados como fontes do
   projeto avaliado. Os arquivos de build do avaliador ficam sob seu controle.

   Reaproveitar instalação dos agents, filas, prepare-ahead, logs, coleta de
   tokens e Docker. Não duplicar o runner para cada modalidade.

5. **Manter o fluxo de execução, com temperatura por modalidade e generator.**

   ```mermaid
   flowchart TD
       A[Configuração e metadados do modelo] --> B[Warmup e calibração de velocidade]
       B --> C[Timeout comum para PI e OpenCode]
       C --> D[Para cada modalidade e generator]
       D --> E[Pré-teste em temperaturas candidatas]
       E --> F[Selecionar temperatura]
       F --> G[Executar desafios em cópias novas]
       G --> H[Testes ocultos em avaliação isolada]
       H --> I[Scores por modalidade e generator]
       I --> J[JSON, Markdown e HTML consolidados]
   ```

   Calibrar uma vez por campanha para o mesmo modelo, endpoint, sampling e
   concorrência, conforme o comportamento atual de `--generator all`. Reutilizar
   o warmup e a regra do request medido mais lento, sem somar throughput para
   calcular o deadline:

   ```text
   timeout = max(minimum, ceil(safety_factor * (token_budget / speed + overhead)))
   ```

   Começar com o mesmo orçamento e deadline nas duas modalidades. O piloto deve
   verificar se leitura de contexto e uso de ferramentas exigem um orçamento
   maior para evolution. Se houver essa mudança, declarar um perfil fixo por
   modalidade e aplicá-lo igualmente aos dois generators, com versão e
   parâmetros registrados. Não ajustar o tempo individualmente conforme o
   resultado de um modelo. O timeout da avaliação Docker continua separado.

   Fazer descoberta para cada par `(suite, generator)`: são até quatro
   temperaturas escolhidas por modelo. A temperatura ideal para escrever do
   zero não precisa ser a ideal para alterar código. Usar as mesmas candidatas,
   o mesmo orçamento e o mesmo critério de desempate: menor temperatura.
   Escolher usando a fórmula final da respectiva modalidade.

   Para evolution, os desafios de descoberta não entram no score final. Hoje
   greenfield reaproveita no resultado os desafios usados na descoberta;
   preservar essa política para manter a série histórica e registrar a
   diferença de protocolo. Uma futura separação também em greenfield deve
   produzir outra versão da suíte, sem recalcular resultados antigos.

   A LLM pode compilar e corrigir o projeto durante a sessão, respeitando o
   deadline e a política de tentativas. Os testes ocultos só rodam depois e seus
   resultados não voltam para a sessão. Se houver timeout, congelar os arquivos
   disponíveis e avaliá-los quando válidos, seguindo a política atual de
   aproveitar a entrega parcial; registrar o timeout separadamente.

   A execução oficial usa as duas modalidades e os dois generators. Preservar
   seleções individuais para desenvolvimento. Exemplos de comandos propostos:

   ```text
   python -m benchmark.cli run --config config.yaml --suite all --generator all
   python -m benchmark.cli run --config config.yaml --suite evolution --generator all
   python -m benchmark.cli list-tasks --suite evolution
   python -m benchmark.cli validate --suite evolution
   ```

   Acrescentar configuração de suíte, mantendo `greenfield` como fallback para
   configurações antigas e configurando `all` no exemplo de execução completa.
   O filtro `--difficulty` deve selecionar apenas os desafios pontuados daquela
   dificuldade; a descoberta de evolution usa seu conjunto fixo de calibração,
   carregado separadamente. Execução de tarefa única é diagnóstico, sem score
   oficial da modalidade completa.

   Evolution acrescenta `2 * (E + D * T)` sessões, com E desafios pontuados,
   D desafios de descoberta e T temperaturas. No piloto, E=6, D=4 e T=4
   representam 44 sessões adicionais. Uma sessão pode conter várias chamadas
   ao modelo. Calibração e descoberta têm custo e tokens registrados à parte.

6. **Pontuar entrega de feature com penalização por regressões.**

   Somar simplesmente pontos de compilação, regressão e feature daria pontos
   ao starter intacto, que já compila e passa nos testes antigos. Recomendo
   usar a fração de requisitos novos atendidos como base e a preservação do
   comportamento existente como multiplicador.

   Para cada desafio, definir pesos explícitos por teste:

   ```text
   F = pontos aprovados de feature / pontos possíveis de feature
   R = pontos aprovados de regressão / pontos possíveis de regressão
   pontos ganhos = pontos possíveis do desafio * F * R

   score_evolution = 100 * soma(pontos ganhos) / soma(pontos possíveis)
   ```

   Proposta inicial: 10 pontos por desafio easy, 20 por medium e 30 por hard.
   Os pesos internos de feature e regressão são normalizados separadamente.
   Assim, o número de testes não altera por acidente o peso total da tarefa.
   Congelar os pesos junto com a versão da suíte. Preservar integralmente os
   pesos e a fórmula de greenfield.

   | Feature F | Preservação R | Score do desafio |
   | --- | --- | --- |
   | 0% | 100% | 0 |
   | 80% | 100% | 80 |
   | 100% | 80% | 80 |
   | 80% | 80% | 64 |
   | 100% | 100% | 100 |

   O build do projeto é pré-requisito, sem pontos próprios em evolution. Se a
   aplicação não compilar, a tarefa recebe zero. Executar regressão e feature
   em projetos de testes separados: uma assinatura nova ausente pode impedir
   a compilação dos testes de feature, mas não deve impedir o diagnóstico dos
   testes antigos. Falha de build da suíte de feature resulta em F=0; falha na
   suíte de regressão resulta em R=0. Ausência de TRX válido nunca equivale a
   sucesso. Testes ausentes, ignorados ou não executados não recebem pontos.

   Reportar F e R separadamente, além do score resultante, para distinguir
   dificuldade de implementação de quebra de comportamento existente. Usar
   testes de integração quando a exigência envolver HTTP, DI ou persistência,
   além dos testes unitários; classes corretas sem integração não entregam
   essas features. A nota mede comportamento e compatibilidade, não qualidade
   arquitetural completa. O diff serve para inspeção, sem um juiz LLM ou
   penalização automática por quantidade de linhas alteradas.

   O denominador de uma execução completa permanece fixo, incluindo tarefas
   com falha. Manter a política atual para erros de infraestrutura, com zero
   e indicação explícita no relatório. Execuções interrompidas ou com tarefas
   não tentadas devem aparecer como incompletas e não disputar o ranking oficial.

7. **Apresentar duas modalidades e o combinado sem confundir as médias.**

   Calcular primeiro por generator:

   ```text
   combinado_pi       = (greenfield_pi + evolution_pi) / 2
   combinado_opencode = (greenfield_opencode + evolution_opencode) / 2

   construção = (greenfield_pi + greenfield_opencode) / 2
   features   = (evolution_pi + evolution_opencode) / 2
   combinado  = (construção + features) / 2
   ```

   O combinado é a média das quatro notas, com peso igual por modalidade e
   generator. Não somar todos os pontos brutos das duas suítes: greenfield tem
   mais desafios e dominaria o resultado. Calcular com os valores não
   arredondados e arredondar apenas para apresentação.

   No HTML, mostrar como colunas principais **Construção**, **Features** e
   **Combinado**. Exibir PI e OpenCode em subcolunas ou detalhes expansíveis:

   | Modelo | Construção PI | Construção OpenCode | Construção | Features PI | Features OpenCode | Features | Combinado |
   | --- | --- | --- | --- | --- | --- | --- | --- |
   | Exemplo | 80 | 84 | 82 | 60 | 68 | 64 | 73 |

   Resultados antigos continuam disponíveis em construção. Features e combinado
   aparecem como `n/a` se faltarem as avaliações necessárias; não preencher com
   zero nem tratar um único resultado como média completa. Uma execução somente
   PI pode exibir seu combinado individual se tiver as duas modalidades, mas
   o combinado oficial do modelo exige as quatro notas.

   Atualizar ordenação, filtros, destaque de melhores valores, gráfico e score
   por GB para indicar qual modalidade está selecionada. Velocidade, timeout,
   temperatura, tokens, F e R devem ficar associados à execução correspondente.
   A visão histórica de construção pode preservar a média atual dos generators
   disponíveis, desde que identificada como histórica/parcial.

   O agregador atual escolhe o melhor resultado disponível por generator, após
   ordenar as execuções por score. Para o ranking novo, usar a última campanha
   completa e compatível por modelo/configuração/versões de suítes e generators.
   Não combinar os melhores scores de campanhas independentes, nem uma tarefa
   isolada com uma suíte completa. Preservar a política antiga apenas na visão
   histórica identificada, sem misturá-la ao ranking oficial novo.

8. **Persistir a identidade da campanha e permitir retomada consistente.**

   Usar um diretório de campanha com `campaign.json`, a calibração compartilhada
   e subdiretórios por `(suite, generator)`. Cada subdiretório mantém descoberta,
   temperatura selecionada, tarefas, `result.json` e `summary.json`. O manifesto
   da campanha liga essas avaliações e informa conclusão e compatibilidade.

   Acrescentar `schema_version`, `campaign_id`, `suite`, `suite_version`,
   `score_formula_version`, IDs/pesos das tarefas, versão de cada generator,
   fingerprints de starter/contrato/testes e hashes da entrega. Guardar F, R,
   resultados por grupo, tempos, tokens, status de sessão e diagnóstico de
   avaliação. Fingerprints são metadados do runner, não conteúdo dado à LLM.

   A retomada reutiliza calibração e temperatura de cada par e executa apenas
   o que faltar. Validar modelo, configuração, concorrência, perfil de timeout,
   suite, generator e fingerprints antes de reutilizar resultados. Se algo
   incompatível mudou, exigir outra campanha. Não escolher novamente a
   temperatura de um par cuja descoberta já terminou.

   Atualizar a coleta do agregador: hoje ela lê `summary.json` apenas nos filhos
   imediatos de `results/`. Ler o manifesto novo, preservando o formato antigo,
   sem coletar summaries da descoberta como se fossem execuções finais.
   Campos estruturados de modalidade e dificuldade substituem a inferência
   pelos prefixos dos IDs novos; manter fallback para os resultados antigos.

9. **Validar a suíte antes de gastar sessões dos modelos.**

   Para cada tarefa de evolution, a validação deve comprovar:

   - Starter compila, passa em todas as regressões e recebe F=0/score=0.
   - Referência com a feature compila, passa em ambos os grupos e recebe 100.
   - Alteração proposital que quebra comportamento antigo reduz R e o score.
   - Feature criada fora do fluxo real da aplicação não passa nos testes de
     integração; implementação incompleta recebe apenas os pontos demonstrados.
   - Testes declarados e seus pesos correspondem aos testes efetivamente
     executados; não há nomes duplicados entre grupos nem testes ignorados.
   - Tempo, IDs, aleatoriedade e dependências externas são controlados; relógio
     injetado, SQLite local e HTTP em memória substituem esperas e serviços reais.

   A validação rápida de metadados permanece disponível. Acrescentar uma opção
   de validação executável, por exemplo `validate --suite evolution --execute`,
   para starter e referência no Docker antes da publicação de uma versão da suíte.

   Nos testes do runner, verificar captura de múltiplos arquivos e remoções,
   isolamento dos testes ocultos, proteção de arquivos imutáveis, build dos
   grupos separados, pontuação de falhas, descoberta por par, retomada e
   agregação completa/parcial. Executar os testes existentes como proteção
   de compatibilidade com greenfield. Depois fazer um piloto real com os dois
   generators e inspecionar diffs, cobertura, tempos e relatórios. Repetições
   para medir variância podem vir depois; quando habilitadas, usar média das
   repetições, nunca escolher a melhor tentativa.

10. **Implementar em etapas pequenas, com resultados verificáveis.**

    | Etapa | Arquivos principais | Entrega verificável |
    | --- | --- | --- |
    | 1. Contrato e loader | `tasks.py`, `config.py`, `cli.py` | Modalidade e papel explícitos; tarefas antigas carregam sem alteração |
    | 2. Artefato do projeto | `generation.py`, `solution.py`, novo `workspace.py`, `runner.py` | Ambos os generators entregam múltiplos arquivos; avaliador usa a entrega real |
    | 3. Primeira tarefa e score | Nova tarefa da pilha, `scorer.py`, `runner.py` | Starter=0, referência=100 e regressão reduz nota |
    | 4. Campanha e descoberta | `cli.py`, `calibration.py`, `report.py` | Matriz de quatro avaliações, calibração compartilhada e retomada consistente |
    | 5. Suíte piloto | Seis tarefas pontuadas, quatro de descoberta e referências | Autoria validada, sem sobreposição entre descoberta e score de evolution |
    | 6. Relatórios | `report.py`, `aggregate_benchmark_results.py`, testes | Duas modalidades, combinado e histórico parcial corretamente identificados |
    | 7. Piloto e documentação | `README.md`, `config.example.yaml`, testes e ADR após decisão | Execução real em PI/OpenCode, versão congelada e comandos documentados |

    A primeira implementação vertical deve ser pequena: tarefa da pilha,
    captura do projeto e score funcionando nos dois generators. Só então
    ampliar o catálogo e o HTML. Essa sequência demonstra primeiro que o
    benchmark consegue observar a mudança real no projeto e detectar regressões.
