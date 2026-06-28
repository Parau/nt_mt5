# AGENTS.md

## 1) Project context
- `nt_mt5` is a NautilusTrader adapter for MetaTrader 5.
- The adapter must translate MT5-native APIs into NautilusTrader's unified interface and normalized domain model.
- The project should follow NautilusTrader's adapter guidance: a clear adapter boundary, a layered design, explicit capability handling, runnable examples, and meaningful automated tests.
- The canonical venue is always `METATRADER_5`.

## 2) Architecture and stable project decisions
- Follow NautilusTrader's layered adapter model:
  - low-level transport, networking, parsing, and bridge concerns in the client layer;
  - Python adapter layer for `DataClient`, `ExecutionClient`, provider, configs, and factories.
- Keep the bridge MT5-native. Do not reintroduce Interactive Brokers semantics, naming, or event models.
- Prefer direct MT5 concepts and APIs only through the terminal-access architecture defined in `docs/terminal_access_contract.md`. Do not bypass `external_rpyc` or `managed_terminal` by introducing ad hoc direct transport paths.
- Translate MT5 -> Nautilus at the adapter boundary. Do not leak bridge-specific, RPyC-specific, or mock-specific objects across the codebase.
- `METATRADER_5` is the structural venue everywhere.
- Broker/server/account details belong in instrument/account metadata, not in venue identity.
- `config.account_id` is the source of truth for validating the MT5 login.
- Nautilus `AccountId` is structural engine identity and must not be parsed to recover the MT5 login.
- The adapter must follow the modern NautilusTrader message contracts for data and execution clients.
- Unsupported operations must fail safely: log a warning or return a controlled empty/unsupported result. Do not raise raw `NotImplementedError` on operational paths.
- Do not reopen these decisions unless a real bug proves they are wrong.

## 3) Production-code rules
- Do not add production logic only to make tests pass.
- Do not add fake-success paths, mock fallbacks, or placeholder terminal/account states that hide real failures.
- Do not reintroduce legacy or hybrid interfaces once a modern typed interface exists.
- Prefer small, explicit fixes over broad redesigns.
- Keep production behavior aligned with actual MT5 capabilities and actual NautilusTrader contracts.
- If a test reveals a real production bug, fix the bug instead of weakening the test.

## 4) Testing rules
- Follow NautilusTrader testing intent and Phase 7 expectations: maintain meaningful unit, integration, acceptance/smoke, performance, and memory-stability coverage.
- Before changing supported/unsupported behavior or test scope, consult:
  - `docs/adapter_contract.md`
  - `docs/testing_contract.md`
  - `docs/data_capability_matrix.md`
  - `docs/execution_capability_matrix.md`
  - `docs/decisions.md`
  - `docs/terminal_access_contract.md`
- Prefer deterministic fakes/stubs over heavy mocking.
- The canonical Tier 1 test infrastructure is `tests/support/fake_mt5_rpyc_bridge.py`. Use it for all integration tests that need an MT5 bridge. Improve the fake when it is insufficient — do not create parallel mocks.
- Use mocks only where they keep the test focused; do not replace most of the adapter with mocks and still call it integration coverage.
- Integration tests should pass through real adapter logic whenever practical.
- Acceptance/smoke tests fall into three layers. **Tier 1** (deterministic, always runs, uses the fake bridge) is the default. **Tier 1.5** (`homologation/` — standalone `TradingNode` runners on real MT5; see `docs/testing_contract.md`) is the operational homologation gate for updating matrix **Live coverage**. **Tier 2** (live acceptance, `tests/acceptance/` with `@pytest.mark.live`) is a selective layer — only add a live test when the fake bridge structurally cannot cover it (real field names, real retcodes, real price constraints, real transport). See `docs/testing_contract.md` — Two-tier validation strategy — for Tier 1/2 criteria; Tier 1.5 is documented in the same file.
- Never add a live test simply because a behavior is important. If the fake bridge can cover it adequately, Tier 1 is the right place.
- Do not end tests with `assert True`.
- Do not use `pytest.skip(...)` to hide missing coverage unless the test is genuinely environment-dependent and a replacement exists.
- Performance tests should use lightweight, stable timing with generous thresholds and should measure real adapter logic, not only mock overhead.
- Memory-stability tests should watch real adapter structures for unintended growth across repeated cycles.
- Organize tests clearly by purpose whenever practical, and prefer reusable fixtures and parametrization over copy-pasted cases.

## 5) Documentation and examples
- Examples must reflect the real public API exactly.
- README, metadata, configs, factories, exports, and examples must stay mutually consistent.
- Keep docs concise, direct, and easy to maintain.
- Document adapter-specific capability limits and behavior clearly, especially supported order types, time-in-force rules, historical/live data support, and unsupported features.
- When compatibility choices are intentional, document them explicitly instead of leaving them implicit.
- Keep these project docs aligned with implementation, tests, and documented support limits:
  - `docs/adapter_contract.md`
  - `docs/testing_contract.md`
  - `docs/data_capability_matrix.md`
  - `docs/execution_capability_matrix.md`
  - `docs/decisions.md`
  - `docs/terminal_access_contract.md`
- When a supported execution or data behavior is implemented or validated live, update the corresponding row in the capability matrix: `Deterministic coverage` if a Tier 1 test was added, `Live coverage` if a Tier 2 test or **Tier 1.5 homologation** scenario passed (`res/proximos testes adaptador.md`).

## 6) PR rules for coding agents
- Stay inside the requested scope.
- Do not declare the work done if core acceptance criteria are still open.
- Do not mix unrelated cleanups into a focused task.
- In each PR, include:
  - a short itemized summary of what changed;
  - the files changed;
  - tests added or updated;
  - any real bug fixes discovered while implementing the task;
  - any intentionally deferred items.
- Separate implementation fixes from test-only fixes.
- If a test reveals a production bug, fix the bug and mention it explicitly.
- If coverage is still partial, say so clearly instead of implying the task is fully complete.

## 7) Source of Truth
For adapter development and testing protocols, you **must** strictly adhere to the official Nautilus Trader developer guidelines:

* **Core Adapter Architecture:** [https://nautilustrader.io/docs/latest/developer_guide/adapters/](https://nautilustrader.io/docs/latest/developer_guide/adapters/)
* **Data Client Specification & Testing:** [https://nautilustrader.io/docs/latest/developer_guide/spec_data_testing/](https://nautilustrader.io/docs/latest/developer_guide/spec_data_testing/)
* **Execution Client Specification & Testing:** [https://nautilustrader.io/docs/latest/developer_guide/spec_exec_testing/](https://nautilustrader.io/docs/latest/developer_guide/spec_exec_testing/)

> **Instruction:** Do not hallucinate class structures or test suites. Align the integration design exactly with the specifications detailed in these official documents.

## 8) Running python
To run python you must set the necessary enviroment variables and use the correct python enviroment with the proper packages installed for example set "MT5_HOST=127.0.0.1" && set "MT5_PORT=18812" && E:\miniconda\envs\trading\python.exe 


Aqui está uma versão aprimorada para o seu `agents.md`. Ela corrige os erros ortográficos ("enviroment"), melhora a clareza dos comandos para o agente de IA e utiliza blocos de código isolados para garantir que a IA entenda a sintaxe exata da execução.

---

## 8) Python Execution Environment

To execute any Python script in this project, you **must** explicitly configure the required environment variables and target the dedicated Conda interpreter to avoid global dependency conflicts.

* **Minimum Required Variables:** `MT5_HOST` (MetaTrader gateway IP) and `MT5_PORT` (TCP socket port) to access the RPyC MT5 bridge.
* **Target Interpreter:** Always use the absolute path of the `trading` environment.

**Execution Template (Windows CMD):**

```cmd
set MT5_HOST=127.0.0.1 && set MT5_PORT=18812 && E:\miniconda\envs\trading\python.exe script_or_python_module.py
```

> **Instruction:** Never invoke a generic `python` command. You must explicitly pass the environment variables inline or verify their state before running any script.

## 9) Code Style and Annotations
STRICT REQUIREMENT: All generated code comments, annotations, and docstrings MUST strictly adhere to the following language and framework-specific constraints. No generic placeholders or narrative comments are allowed.

**Preserve Existing Documentation:** Never delete, strip, or overwrite existing comments within the codebase unless they are strictly deprecated, obsolete, or directly impacted/invalidated by the new code changes or refactoring.

### **Python:** 
 - MANDATORY: Use native type hints for all public functions, methods, and service/model boundaries.
 - REQUIRED: Write concise Google Style docstrings for trading rules, side effects, non-obvious core logic, Application Service API boundaries, Provider SPI / Transport SPI boundaries, Integration Adapter boundaries, and other public boundary objects. When necessary add comments with architectural Notes.
### **MQL5 Code**  
 - **Document the "Why", Not the "What":** Avoid trivial or redundant comments (e.g., do not write `// loops through the array`). Instead, explicitly document the mathematical, quantitative, or networking intent (e.g., `// Reverses the array topology so index [0] strictly represents the forming candle`).
  - **Network & Execution Critical Paths:** Every native socket operation (`SocketCreate`, `SocketReceive`) and structural trade submission (`OrderSend`) must feature brief inline comments detailing buffer allocations, state expectations, or specific error-handling reasons.
  - **Zero AI Conversational Fillers:** Never insert generic placeholders, conversational markers, or useless templates (such as `// Add your logic here` or `// Prepared by AI`). Code must be production-ready and fully articulated.
 