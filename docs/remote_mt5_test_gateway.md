# Gateway Remoto de Teste (RPyC) — Documento Operacional

Este documento descreve o papel, o propósito e o funcionamento do gateway remoto RPyC utilizado para validação operacional suplementar do adaptador `nt_mt5`.

## Propósito

O gateway remoto é uma **ferramenta operacional de suporte e infraestrutura externa**, destinada exclusivamente à validação em tempo real (*live validation*) do adaptador em ambientes onde o terminal MetaTrader 5 (MT5) está disponível nativamente (tipicamente Windows).

Este gateway representa a implementação operacional concreta para o modo de acesso **`EXTERNAL_RPYC`**, atuando como a bridge de comunicação entre o adaptador e o terminal MT5.

Ele permite que desenvolvedores e contribuidores validem a conectividade, a recepção de dados e a execução de ordens contra um terminal MT5 real em um ambiente controlado, sem a necessidade de gerenciar o ciclo de vida do terminal através do adaptador.

**Atenção:** Este gateway e a prática de *live validation* são secundários e suplementares. Eles **não substituem** a suíte de testes determinística principal (unitários e de integração com fakes) definida no contrato de testes do projeto.

## Papel no Projeto e Alinhamento Arquitetural

Para garantir a hierarquia correta entre contratos arquiteturais e ferramentas operacionais, o papel deste gateway é definido pelos seguintes pilares:

1.  **Implementação de `EXTERNAL_RPYC`**: O gateway remoto é a implementação operacional concreta do modo de acesso `MT5TerminalAccessMode.EXTERNAL_RPYC`. Ele representa um terminal ou bridge que já existe e é operado fora do escopo de gerenciamento do adaptador.
2.  **Suporte à Validação Operacional**: Seu uso é restrito a testes de aceitação e fumaça em ambiente real. Ele deve ser tratado como uma ferramenta de diagnóstico e não como parte do núcleo arquitetural estável.
3.  **Independência de Lifecycle**: Este gateway **não** faz parte do modo `MANAGED_TERMINAL`. O adaptador não possui responsabilidade sobre o início, supervisão ou encerramento do processo deste gateway.
4.  **Distinção de Backends**: Embora o gateway possa ser executado em containers para conveniência, ele não deve ser confundido com o backend `DOCKERIZED` planejado para o modo gerenciado. Sua arquitetura é puramente de transporte RPC externo.
5.  **Subordinação aos Contratos**: Este componente não redefine o modelo de acesso ao terminal. Ele deve seguir estritamente as definições estabelecidas em `docs/adapter_contract.md` e `docs/terminal_access_contract.md`.

## Modelo de Configuração

O uso deste gateway é regido pela configuração de `terminal_access`. Quando o adaptador é configurado para `EXTERNAL_RPYC`, ele espera uma estrutura de `ExternalRPyCTerminalConfig` contendo:

- `host`: Endereço IP ou hostname onde o gateway está ouvindo.
- `port`: Porta RPyC configurada no gateway (padrão `18812`).
- `label`: Rótulo opcional para identificação da conexão.
- Parâmetros opcionais de timeout e keep-alive conforme definido no contrato de conexão.

O adaptador atua como um cliente puro, assumindo que o gateway já está pronto e operacional.

## Regras de Uso e Limites Operacionais

1.  **Ambiente Nativo**: O gateway exige a execução em um ambiente (físico ou VM) onde a biblioteca `MetaTrader5` possa se comunicar com um terminal MT5 instalado e logado.
2.  **Uso em CI**: Em ambientes de CI, este gateway só deve ser utilizado em etapas de validação assistida ou integração live específica, nunca bloqueando a suíte principal de testes offline.
3.  **Segurança**: Por utilizar RPyC, o gateway deve ser operado em redes seguras ou através de túneis criptografados, visto que expõe capacidades de execução de ordens no terminal MT5.
4.  **Estabilidade**: Falhas no gateway (como perda de conexão RPC) devem ser tratadas pelo adaptador como falhas de transporte, sem comprometer a integridade dos parsers internos.

## Política de testes live

Testes que exigem este gateway são testes live e devem ser tratados como validação operacional suplementar.

Eles devem:

- viver em `tests/live/` ou ser explicitamente marcados como live;
- usar `@pytest.mark.live`;
- usar `@pytest.mark.external_rpyc` quando dependerem do gateway RPyC real;
- usar `@pytest.mark.demo_execution` quando puderem submeter ordens;
- pular automaticamente quando variáveis de ambiente obrigatórias estiverem ausentes;
- nunca bloquear a suíte determinística padrão;
- nunca substituir testes unitários ou de integração com fake bridge.

Testes de execução live devem exigir opt-in explícito:

```text
MT5_ENABLE_LIVE_EXECUTION=1
```

Variáveis típicas para validação live incluem:

```text
MT5_HOST
MT5_PORT
MT5_ACCOUNT_NUMBER
MT5_SERVER
MT5_TEST_SYMBOL
MT5_TEST_ORDER_QTY
MT5_ENABLE_LIVE_EXECUTION
```

O comando padrão de regressão deve continuar excluindo testes live, por exemplo:

```bash
pytest -m "not live"
```

Um smoke live de dados pode ser executado explicitamente, por exemplo:

```bash
pytest -m "live and external_rpyc" tests/live/test_external_rpyc_data_smoke.py
```

Um smoke live de execução demo deve exigir opt-in explícito, por exemplo:

```bash
MT5_ENABLE_LIVE_EXECUTION=1 pytest -m "live and external_rpyc and demo_execution" tests/live/test_external_rpyc_exec_smoke.py
```

## Fluxo de Operação

Ao conectar-se via `MT5TerminalAccessMode.EXTERNAL_RPYC`, o adaptador estabelece um link RPC. O gateway atua como um proxy transparente para a API nativa do MetaTrader 5, devolvendo resultados brutos que são normalizados pelo adaptador na camada de borda, transformando-os em tipos de domínio do NautilusTrader.

## Relação com outros Documentos

Para entender a base arquitetural que sustenta este gateway, consulte:

- **`docs/adapter_contract.md`**: Define a arquitetura em camadas do adaptador e como ele consome o transporte venue-native.
- **`docs/terminal_access_contract.md`**: Estabelece o contrato público e os modos de acesso (`EXTERNAL_RPYC` vs `MANAGED_TERMINAL`).
- **`docs/testing_contract.md`**: Define a estratégia de testes e deixa claro que a suíte determinística principal é a autoridade de correção, não a validação via gateway.
- **`docs/decisions.md`**: Registra as decisões estáveis de arquitetura (como o venue `METATRADER_5`) que este gateway deve respeitar.
- **`docs/specs/spec_terminal_access_with_gateway.md`**: Contém a especificação técnica detalhada da superfície RPC suportada e serve como a principal referência arquitetural para este modo de acesso.
- **`docs/ai_agent_guidelines.md`**: Define regras para evitar que agentes confundam validação live com regressão determinística.
- **`docs/contract_tests_plan.md`**: Planeja testes de contrato para garantir que live tests permaneçam opcionais e seguros.

---

**Nota:** Este gateway é considerado uma ferramenta de infraestrutura externa suplementar. O suporte oficial do adaptador é construído para ser agnóstico ao provedor RPyC, desde que este respeite a interface de baixo nível acordada.
