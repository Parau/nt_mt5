# Especificação — arquitetura de acesso ao terminal MT5 (`external_rpyc` + `managed_terminal`)

## Objetivo

Implementar no `nt_mt5` uma arquitetura pública e estável para acesso ao terminal MT5 que:

- suporte agora o acesso por **`external_rpyc`**, quando o adapter consome um gateway RPyC já existente
- introduza desde já o conceito público de **`managed_terminal`**, para quando o próprio adapter for responsável por iniciar, supervisionar e encerrar o ambiente do terminal
- deixe preparado, para fase futura, um backend **`dockerized`** dentro de `managed_terminal`, sem redesenhar novamente a API pública

## Referências upstream

Esta especificação foi revisada para ficar em sintonia com a documentação oficial do NautilusTrader para desenvolvimento e testes de adapters:

- Adapters: https://nautilustrader.io/docs/latest/developer_guide/adapters/
- Testing Guide: https://nautilustrader.io/docs/latest/developer_guide/testing/
- Data Testing Spec: https://nautilustrader.io/docs/latest/developer_guide/spec_data_testing/
- Execution Testing Spec: https://nautilustrader.io/docs/latest/developer_guide/spec_exec_testing/

Se houver conflito entre esta especificação e o contrato upstream do NautilusTrader, o upstream deve prevalecer, exceto onde o projeto registrar explicitamente uma decisão local em `docs/decisions.md`.

## Alinhamento técnico com NautilusTrader

Esta proposta segue os princípios que a documentação oficial do NautilusTrader recomenda para adapters:

- arquitetura em camadas
- camada de baixo nível mantendo conceitos nativos do venue
- camada Python do adapter concentrando `InstrumentProvider`, `LiveDataClient`, `LiveExecutionClient`, configs e factories
- tradução de MT5 para o modelo unificado do Nautilus na borda do adapter
- documentação explícita de capacidades suportadas e não suportadas
- suíte de testes dividida em:
  - unit tests
  - integration tests
  - acceptance tests
  - performance tests
  - memory leak tests
- validação do adapter contra o subconjunto aplicável das capabilities que ele realmente suporta

## Problema de arquitetura considerado e solução adotada

### Problema considerado

O projeto precisa suportar dois cenários estruturalmente diferentes de acesso ao MT5:

1. **terminal ou gateway já existente fora do adapter**
   - exemplo: sandbox, CI assistido, máquina remota, túnel privado, gateway iniciado por outro processo
2. **terminal gerenciado pelo próprio adapter**
   - exemplo futuro: execução local em que o adapter deve levantar, supervisionar e encerrar o ambiente do MT5

A dúvida arquitetural é se a API pública deveria ser modelada em torno do **tipo de acesso ao terminal** ou em torno do **mecanismo interno de hospedagem**, como `dockerized`.

### Solução adotada

A API pública do adapter deve representar **como o terminal é acessado**, não **como ele é hospedado internamente**.

Portanto, a modelagem pública deve distinguir:

- `external_rpyc`
- `managed_terminal`

e não usar `dockerized` como o conceito público principal.

### Justificativa

`external_rpyc` e `managed_terminal` representam cenários diferentes de responsabilidade e lifecycle:

- em `external_rpyc`, o terminal ou gateway já existe fora do adapter
- em `managed_terminal`, o adapter passa a ser responsável por iniciar, supervisionar e encerrar o ambiente do terminal

Já `dockerized` é apenas uma **estratégia de implementação** futura de `managed_terminal`, e não a abstração arquitetural principal que usuários e contribuidores devem enxergar.

## Situação atual do gateway remoto já existente

### Premissa importante desta especificação

O caminho `external_rpyc` **não parte de um gateway hipotético**.
Já existe uma implementação funcional de gateway remoto em Python, executada fora do adapter, que encapsula a biblioteca `MetaTrader5` em outro computador e expõe uma interface RPyC para o adapter consumir.

Portanto, nesta fase do projeto:

- o trabalho principal é **integrar o adapter ao gateway já existente**
- a especificação **não exige redesenhar o gateway remoto**
- a primeira implementação de `external_rpyc` deve se alinhar à superfície RPC já disponível, adicionando apenas as adaptações necessárias no lado do adapter

### Papel arquitetural desse gateway

O gateway remoto existente deve ser tratado como parte da **camada de baixo nível venue-native** do sistema.

Ele já cumpre o papel de:

- encapsular chamadas para `MetaTrader5` Python
- expor um endpoint RPyC consumível pelo adapter
- executar as operações MT5 em um ambiente onde o terminal real está disponível
- devolver ao adapter os resultados brutos do MT5 para normalização na borda

Em termos de arquitetura do NautilusTrader, isso reforça que:

- o gateway remoto pertence à camada de infraestrutura/transport/venue-native
- o adapter permanece responsável pela tradução para o modelo do Nautilus
- a decisão de usar esse gateway continua concentrada em configs e factories

### Superfície RPC já disponível hoje

A implementação atual do gateway remoto já expõe, no mínimo, os seguintes métodos:

#### Sessão e diagnóstico

- `initialize`
- `login`
- `last_error`
- `version`
- `shutdown`
- `get_constant`

#### Estado do terminal e da conta

- `terminal_info`
- `account_info`

#### Símbolos e seleção

- `symbols_get`
- `symbol_info`
- `symbol_info_tick`
- `symbol_select`

#### Histórico e market data

- `copy_rates_from_pos`
- `copy_ticks_range`
- `copy_ticks_from`

#### Execução e histórico operacional

- `order_send`
- `positions_get`
- `history_orders_total`
- `history_orders_get`
- `history_deals_total`
- `history_deals_get`

### Implicações para o adapter

A primeira implementação do modo `external_rpyc` deve:

- assumir essa superfície RPC como contrato operacional inicial
- evitar inventar dependências obrigatórias em métodos que o gateway ainda não expõe
- adaptar o client do adapter para normalizar os retornos RPyC e convertê-los em estruturas Python puras e, depois, em tipos do Nautilus

Se futuramente o gateway for ampliado com operações adicionais como `orders_get` ou `order_check`, isso pode ser absorvido sem mudar a modelagem pública de `terminal_access`.

### Consequência para o escopo

Nesta atividade, `external_rpyc` significa especificamente:

- consumir um gateway remoto já pronto
- integrar-se ao contrato RPC atual desse gateway
- documentar claramente as capabilities já disponíveis e as lacunas conhecidas

Não significa:

- projetar uma abstração de transporte genérica desligada do MT5
- exigir paridade imediata com todas as APIs potenciais do MetaTrader5 Python
- condicionar a arquitetura pública à implementação futura do backend `dockerized`

## Escopo desta atividade

### Incluir agora

- introdução do novo conceito público de acesso ao terminal
- implementação funcional do caminho `external_rpyc`
- integração do adapter com o gateway remoto RPyC já existente
- adaptação de configs, factories, cache e documentação
- compatibilização com o client compartilhado atual
- testes unitários, de integração e acceptance do novo caminho
- preparação explícita para `managed_terminal`

### Não incluir agora

- implementação completa do runtime `managed_terminal`
- implementação do backend `dockerized`
- subida real de terminal MT5 em Docker
- redesign amplo do núcleo do adapter fora do necessário para suportar o novo modelo
- redesign do gateway remoto existente além de ajustes pontuais estritamente necessários à integração

## Resultado esperado

Ao final desta atividade, o projeto deve permitir declarar de forma explícita e estável:

- “este adapter acessa um terminal MT5 por `external_rpyc`”
- e, no futuro:
  - “este adapter usa `managed_terminal`”
  - e dentro dele escolhe um backend como `dockerized` ou outro launcher local

Além disso, deve ficar claro na documentação do projeto que:

- o gateway remoto atual já existe
- `external_rpyc` integra esse gateway existente
- `managed_terminal` é a via prevista para quando o adapter passar a controlar o ciclo de vida do terminal

## Modelo público proposto

### 1. Conceito público: `terminal_access`

Adicionar nas configs públicas do adapter um conceito explícito de acesso ao terminal.

#### Enum pública sugerida

```python
class MT5TerminalAccessMode(Enum):
    EXTERNAL_RPYC = "external_rpyc"
    MANAGED_TERMINAL = "managed_terminal"
```

O nome exato pode variar para seguir o estilo do projeto, mas a semântica deve ser esta.

#### Regra

Este enum deve se tornar a principal representação pública de **como o terminal é acessado**.

Ele deve substituir gradualmente o papel arquitetural hoje distribuído entre:

- `mode`
- `rpyc_config`
- `dockerized_gateway`

quando esses campos estiverem sendo usados para inferir, de forma implícita, o modo de acesso ao terminal.

### 2. Config pública para `external_rpyc`

Criar ou consolidar uma config pública específica para o acesso externo via RPyC.

#### Estrutura sugerida

```python
@dataclass(frozen=True)
class ExternalRPyCTerminalConfig:
    host: str
    port: int
    keep_alive: bool = False
    timeout_secs: float | None = None
    label: str | None = None
```

#### Regras

- `host` e `port` são obrigatórios
- a config deve ser puramente declarativa
- a config deve representar um endpoint de gateway já existente
- a config não deve carregar lógica de lifecycle de terminal
- a config deve ser segura para cache e composição de chave determinística

#### Uso esperado

Este modo cobre cenários como:

- sandbox do agente
- validação remota via túnel privado
- gateway privado já executando em outra máquina
- ambiente local em que o gateway já foi iniciado por outro processo

### 3. Config pública para `managed_terminal`

Mesmo sem implementação completa agora, a forma pública deve ser introduzida desde já.

#### Estrutura sugerida

```python
@dataclass(frozen=True)
class ManagedTerminalConfig:
    backend: str
    startup_timeout_secs: float | None = None
    shutdown_timeout_secs: float | None = None
    healthcheck_timeout_secs: float | None = None
```

#### Enum futura sugerida

```python
class ManagedTerminalBackend(Enum):
    LOCAL_PROCESS = "local_process"
    DOCKERIZED = "dockerized"
```

#### Comportamento nesta fase

- `managed_terminal` deve existir como caminho arquitetural previsto
- se ainda não estiver implementado, deve falhar de forma controlada e explícita
- a documentação deve deixar claro que `dockerized` é backend futuro de `managed_terminal`

## Configs principais do adapter

As configs públicas de data client e execution client devem migrar para um formato semelhante a este:

```python
@dataclass(frozen=True)
class MetaTrader5DataClientConfig(...):
    terminal_access: MT5TerminalAccessMode
    external_rpyc: ExternalRPyCTerminalConfig | None = None
    managed_terminal: ManagedTerminalConfig | None = None
    ...
```

```python
@dataclass(frozen=True)
class MetaTrader5ExecClientConfig(...):
    terminal_access: MT5TerminalAccessMode
    external_rpyc: ExternalRPyCTerminalConfig | None = None
    managed_terminal: ManagedTerminalConfig | None = None
    ...
```

## Regras de validação das configs

### Quando `terminal_access == external_rpyc`

- `external_rpyc` é obrigatório
- `managed_terminal` deve ser `None` ou rejeitado com mensagem clara
- o adapter deve usar exatamente o endpoint informado
- o adapter deve assumir que o gateway remoto já existe e é externo ao seu lifecycle

### Quando `terminal_access == managed_terminal`

- `managed_terminal` é obrigatório
- `external_rpyc` deve ser `None` ou rejeitado com mensagem clara
- se o backend ainda não estiver implementado, falhar com erro controlado e mensagem explícita

### Proibido

- inferir automaticamente o modo com base em campos parcialmente preenchidos
- manter decisões implícitas demais nas factories
- misturar os dois modos silenciosamente

## Factories

### Objetivo

As factories devem ser o ponto central de decisão do wiring, conforme a arquitetura recomendada para adapters do NautilusTrader.

### Regras obrigatórias

#### 1. Centralizar a decisão de acesso ao terminal nas factories

As factories devem:

- ler `terminal_access`
- validar a config correspondente
- construir o client compartilhado correto
- devolver os clients do adapter conectados ao transporte adequado

#### 2. Caminho `external_rpyc`

Quando `terminal_access == external_rpyc`:

- usar a config `external_rpyc`
- construir o client compartilhado MT5 apontando para `host` e `port`
- integrar o client compartilhado à superfície RPC já existente do gateway remoto
- não iniciar terminal local
- não assumir controle de lifecycle do terminal remoto
- controlar apenas a conexão do adapter com o gateway

#### 3. Caminho `managed_terminal`

Quando `terminal_access == managed_terminal`:

- delegar para um componente de terminal manager ou launcher
- nesta fase, se ainda não implementado, retornar erro controlado de capability não disponível
- deixar explícito no código onde o backend futuro será conectado

### Estrutura interna sugerida

Separar o wiring em componentes explícitos, por exemplo:

- `build_external_rpyc_client(...)`
- `build_managed_terminal_client(...)`

ou equivalente

Isso evita decisões espalhadas em múltiplos módulos.

## Client compartilhado e cache

### Regra principal

O cache do client compartilhado deve refletir o **modo efetivo de acesso ao terminal**.

A chave de cache deve incluir pelo menos:

- `terminal_access`
- `client_id`
- host e porta efetivos de `external_rpyc`
- backend efetivo de `managed_terminal`, quando existir
- parâmetros resolvidos relevantes

#### Exemplo conceitual

```python
(
    terminal_access,
    client_id,
    external_rpyc_host,
    external_rpyc_port,
    managed_backend,
)
```

### Requisitos

- não mutar config congelada para completar campos
- não usar identidade de objeto como base do cache
- não esconder resolução dinâmica em estados implícitos

## Client de baixo nível

### Regras para `external_rpyc`

O client de baixo nível deve continuar MT5-native.

Ele deve:

- conectar ao gateway RPyC externo
- consumir a superfície RPC já exposta pelo gateway existente
- normalizar netrefs e objetos remotos em estruturas Python puras na borda
- expor operações MT5-native para o restante do adapter

#### Operações mínimas que a integração deve considerar disponíveis

- `initialize`
- `login`
- `last_error`
- `version`
- `terminal_info`
- `account_info`
- `symbols_get`
- `symbol_info`
- `symbol_info_tick`
- `symbol_select`
- `copy_rates_from_pos`
- `copy_ticks_range`
- `copy_ticks_from`
- `order_send`
- `positions_get`
- `history_orders_total`
- `history_orders_get`
- `history_deals_total`
- `history_deals_get`
- `shutdown`
- `get_constant`

#### Regra de adaptação

O adapter deve tratar esse conjunto como a superfície mínima disponível nesta fase.
Se o adapter precisar de comportamento adicional para uma capability futura, isso deve ser resolvido por uma destas vias:

- composição a partir dos métodos já existentes
- extensão explícita do gateway remoto
- degradação segura da capability, quando ela ainda não for suportada

### Proibido

- adicionar uma abstração genérica demais que descaracterize MT5
- reintroduzir semântica herdada de IB
- misturar responsibility de lifecycle de terminal com parsing de payloads
- presumir, sem validação, a existência de métodos que o gateway atual não expõe

## Preparação para `managed_terminal`

Mesmo sem implementar o runtime completo agora, o projeto deve ganhar um ponto de extensão explícito.

### Estrutura interna sugerida

```python
class ManagedTerminalLauncher(Protocol):
    async def start(self) -> ResolvedTerminalEndpoint: ...
    async def stop(self) -> None: ...
    async def healthcheck(self) -> None: ...
```

onde `ResolvedTerminalEndpoint` poderia ser algo como:

```python
@dataclass(frozen=True)
class ResolvedTerminalEndpoint:
    host: str
    port: int
```

### Benefício

Isso permite que, no futuro, backends como:

- `dockerized`
- `local_process`
- outro launcher local

produzam apenas um endpoint resolvido para o mesmo client MT5 já existente.

Ou seja:

- o backend gerenciado resolve **como levantar o terminal**
- o client compartilhado continua resolvendo **como falar com o terminal**

## Lifecycle esperado

### Para `external_rpyc`

#### O adapter é responsável por:

- abrir e fechar a conexão com o gateway
- validar disponibilidade mínima do terminal
- validar conta MT5 esperada no execution client
- manter `ready-state` coerente

#### O adapter não é responsável por:

- iniciar o terminal remoto
- encerrar o terminal remoto
- supervisionar o processo do gateway remoto além do nível de conectividade

### Para `managed_terminal` no futuro

#### O adapter será responsável por:

- iniciar o backend de terminal
- aguardar `healthcheck`
- obter endpoint resolvido
- conectar ao terminal
- encerrar o runtime gerenciado no shutdown

## Estados, erros e comportamento operacional

### `external_rpyc`

Falhas devem ser explícitas e separadas por tipo:

- endpoint inacessível
- bridge respondeu, mas MT5 não está disponível
- conta logada diferente da esperada
- `terminal_info` indisponível
- capability não suportada
- método ausente no gateway para uma operação ainda não implementada

### Regras

- falhar cedo e com mensagem precisa
- não mascarar estado com valores fake
- não preencher estado “Mock”
- não setar `ready-state` antes do bootstrap real
- não lançar `NotImplementedError` cru em caminhos operacionais; usar erro controlado ou resultado suportado/vazio conforme o contrato do client

## Compatibilidade e migração

### Objetivo

Introduzir o novo modelo sem quebrar desnecessariamente o projeto, mas sem perpetuar ambiguidade arquitetural.

### Estratégia recomendada

#### Fase 1 — introdução do novo modelo

- adicionar `terminal_access`
- adicionar `external_rpyc`
- adicionar `managed_terminal`
- atualizar factories para usar o novo caminho
- integrar o caminho `external_rpyc` à superfície RPC atual do gateway remoto
- manter compatibilidade mínima com o modelo anterior apenas durante transição curta

#### Fase 2 — limpeza

- remover campos antigos redundantes quando o novo modelo estiver estável
- eliminar decisões implícitas baseadas em `dockerized_gateway` como conceito público principal
- deixar `dockerized` apenas como backend interno de `managed_terminal`

### Regra importante

Não manter duas arquiteturas públicas concorrentes por muito tempo.

## Documentação obrigatória

Atualizar os documentos do projeto para refletir esta decisão.

### 1. `docs/adapter_contract.md`

Adicionar ou ajustar para deixar explícito que:

- o adapter separa `external_rpyc` de `managed_terminal`
- `external_rpyc` integra um gateway remoto já existente e MT5-native
- `dockerized` é backend futuro do terminal gerenciado, não modo público principal

### 2. `docs/decisions.md`

Registrar como decisão estável:

- o adapter adota `external_rpyc` e `managed_terminal` como modos públicos
- `external_rpyc` é implementado primeiro sobre o gateway remoto já disponível
- `dockerized` não é a abstração principal da arquitetura
- `dockerized` fica reservado como backend futuro de `managed_terminal`

### 3. `docs/remote_mt5_test_gateway.md`

Se este documento existir ou for reintroduzido, alinhá-lo ao novo modelo:

- gateway remoto privado é caso de `external_rpyc`
- o gateway já existe e expõe uma superfície RPC MT5-native concreta
- não é `dockerized`
- não é `managed_terminal`

### 4. README e examples

Atualizar examples e README para mostrar:

#### Exemplo atual

configuração via `external_rpyc`

#### Exemplo futuro documentado

`managed_terminal` com backend `dockerized` como capability planejada, não implementada ainda

## Testes obrigatórios

Esta atividade deve ficar em sintonia com o Testing Guide do NautilusTrader e com os Data/Execution Testing Specs.

### 1. Unit tests

Adicionar ou ajustar testes para:

- validação de config de `terminal_access`
- erro quando `external_rpyc` está ausente no modo correspondente
- erro quando `managed_terminal` está ausente no modo correspondente
- chave de cache incluindo `terminal_access`
- factories escolhendo o caminho correto
- `external_rpyc` não iniciando terminal local
- normalização de endpoint resolvido para o client compartilhado
- normalização de netrefs e retornos do gateway atual

### 2. Integration tests

Com fake bridge determinística que reflita a superfície do gateway remoto já existente, validar:

- `connect` e `disconnect` com `external_rpyc`
- bootstrap de conta e terminal via `external_rpyc`
- fluxo de data e execution usando o client real do adapter sobre fake bridge
- falha controlada para `managed_terminal` enquanto o backend não estiver implementado
- comportamento correto quando o gateway não expõe um método ainda não suportado

### 3. Acceptance or smoke tests

Adicionar pelo menos:

- teste de wiring público das configs novas
- teste do example principal com `external_rpyc`
- teste garantindo que README e example não usam terminologia arquitetural antiga conflitante

### 4. Performance tests

Adicionar pelo menos testes leves para detectar regressão grosseira em:

- criação e resolução do wiring de `external_rpyc`
- transformação de configs em endpoint resolvido
- rotinas críticas de parsing ou bootstrap afetadas por esta mudança

### 5. Memory leak tests

Adicionar pelo menos verificações leves de estabilidade para:

- ciclos repetidos de `connect` e `disconnect`
- criação repetida de clients com mesma config
- inexistência de crescimento indevido em estruturas internas ligadas ao modo de acesso

### 6. Alinhamento com os specs do Nautilus

- o adapter deve continuar validando o subconjunto aplicável do `Data Testing Spec`
- o adapter deve continuar validando o subconjunto aplicável do `Execution Testing Spec`
- o adapter guide do projeto deve deixar claro quais capabilities do MT5 estão disponíveis já no gateway remoto atual e quais dependem de extensão futura
- quando o modo `managed_terminal` existir de fato, os testes do projeto devem deixar claro se esse modo participa dos mesmos fluxos tester-based ou apenas do wiring inicial

## Critérios de aceite

Esta atividade só estará concluída quando:

1. existir um conceito público explícito equivalente a `terminal_access`
2. `external_rpyc` estiver implementado e funcional no adapter
3. a implementação de `external_rpyc` estiver alinhada ao gateway remoto RPyC já existente
4. `managed_terminal` estiver previsto na API pública e no wiring interno
5. `dockerized` estiver posicionado como backend futuro de `managed_terminal`, não como modo público principal
6. factories e cache estiverem alinhados ao novo modelo
7. documentação e examples refletirem a nova arquitetura
8. houver testes cobrindo o novo caminho e sua preparação futura
9. a proposta permanecer coerente com o modelo em camadas e o contrato de testing do NautilusTrader

## Não objetivos

Esta atividade não deve:

- redesenhar novamente a semântica de data e execution já estabilizada
- reabrir a decisão de venue canônico
- reintroduzir nomenclatura de IB
- transformar a bridge MT5-native em abstração genérica demais
- exigir live tests com MT5 real como pré-requisito desta etapa

## Resumo executivo

Implementar agora:

- **modo público `external_rpyc`**
- **integração com o gateway remoto RPyC já existente**

Preparar agora:

- **modo público `managed_terminal`**

Reservar para fase futura dentro de `managed_terminal`:

- **backend `dockerized`**

Em termos arquiteturais:

- `external_rpyc` e `managed_terminal` são decisões públicas de acesso ao terminal
- o gateway remoto atual já existe e pertence ao caminho `external_rpyc`
- `dockerized` é uma estratégia interna futura do terminal gerenciado
- configs e factories são o lugar correto para concentrar essa decisão
- o client de baixo nível continua MT5-native
- o adapter continua traduzindo MT5 → Nautilus na borda
