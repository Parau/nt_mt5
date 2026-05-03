> [!IMPORTANT]
> This is an independent MetaTrader 5 adapter intended for use with NautilusTrader-compatible workflows.
>
> This project is not affiliated with Nautech Systems Pty Ltd or the NautilusTrader project, is not endorsed by Nautech Systems Pty Ltd or the NautilusTrader project, and is not supported by Nautech Systems Pty Ltd or the NautilusTrader project.
>
> “NautilusTrader” is used only to describe compatibility with the NautilusTrader open-source trading framework. This project is not an official NautilusTrader adapter, package, or integration.
> 

# Nautilus MetaTrader 5 Adapter 🌟

This adapter allows for seamless integration between NautilusTrader and MetaTrader 5, providing capabilities for market data retrieval, order execution, and account management. It supports remote terminal access through a dedicated RPyC bridge and high-speed data streaming via MetaTrader 5 Expert Advisors (EA).

> [!WARNING]
> This project is experimental and under development.
>
> It is provided for research, testing, and educational purposes only. It is not production-ready and should not be used in live trading environments, with live trading accounts, or with real funds.
>
> APIs, behavior, configuration, and compatibility may change without notice. No warranty is provided, and use of this project is entirely at your own risk.

## Terminal Access Modes 🛠️

The adapter architecture distinguishes between three main access modes:

1. **External RPyC Mode (`EXTERNAL_RPYC`)** 🌐 — **Currently Supported**
   - Connects to an existing MT5 RPyC bridge (e.g., running on a remote Windows machine or a separate container).
   - The adapter does not manage the lifecycle of the terminal; it assumes the bridge is already operational.
   - This is the recommended path for immediate use and remote terminal access.

2. **Local Python Mode (`LOCAL_PYTHON`)** 🖥️ — **Supported**
   - Uses the official `MetaTrader5` Python package installed directly on the local machine (Windows only).
   - No RPyC gateway or external bridge is involved; the adapter calls MT5 functions directly.
   - Fails with an explicit, controlled error on incompatible platforms or if the package is not installed.
   - Use `LocalPythonTerminalConfig` to configure this mode.

3. **Managed Terminal Mode (`MANAGED_TERMINAL`)** 📦 — **Planned**
   - Designed for scenarios where the adapter manages the terminal lifecycle (starting, health-checking, and stopping).
   - Will support different backends, such as `DOCKERIZED` (internal strategy for running MT5 in a container).
   - **Note:** This mode is currently under development and not yet operational (raises `RuntimeError`).

## Communication Modes 📡

Within the chosen terminal access mode, the adapter uses different communication strategies:

- **IPC Mode**: Standard MetaTrader 5 Python integration, leveraged via the RPyC bridge to support Linux and remote environments.
- **Socket Mode (EA)**:
   - Connects to a MetaTrader 5 Expert Advisor (EA) for low-latency streaming.
   - Ideal for real-time market data updates and fast execution.

## Nomenclature Clarity 📖

To avoid confusion, please note the following nomenclature used throughout this project:
- **Repository Name**: `nt_mt5` (e.g. `Parau/nt_mt5`)
- **Distribution Name**: `nautilus-mt5` (the package name used in `pyproject.toml`)
- **Python Import Name**: `nautilus_mt5` (used in Python code, e.g. `import nautilus_mt5`)

## Installation ⚙️

To install the MetaTrader 5 Adapter, follow these steps:

1. **Clone the repository:**
   ```sh
   git clone https://github.com/Parau/nt_mt5.git
   ```

2. **Navigate to the project directory:**
   ```sh
   cd nt_mt5
   ```

3. **Install the required Python packages** (we use `uv` but you can use `pip`):
   ```sh
   uv pip install -e .
   ```

> **Note:** Docker is not required for the default `EXTERNAL_RPYC` mode.

## Usage 🖥️

The primary way to use the adapter is via the `EXTERNAL_RPYC` mode, connecting to an existing bridge.

```bash
cd examples
cp .env.example .env
# Edit .env with your MT5 credentials and bridge host/port
uv run python connect_with_external_rpyc.py
```

**NOTE:** Ensure you have a running MT5 RPyC bridge accessible at the host and port specified in your `.env` file. ⚠️

### Detailed Steps:

1. Clone the repository and navigate to the project directory (`nt_mt5`).
2. Install the required Python packages (`uv pip install -e .`).
3. Navigate to the `examples` directory.
4. Copy the `.env.example` file to `.env` and configure it with your MetaTrader 5 credentials and bridge connection details.
5. Ensure your MT5 RPyC bridge is running (typically on a Windows machine or a container).
6. Run the `connect_with_external_rpyc.py` script to start the adapter.

## Project Structure 🗂️

The project structure is organized as follows:

```
nautilus_mt5/
├── nautilus_mt5/            # Adapter source code
│   ├── config.py            # Config classes (ExternalRPyCTerminalConfig, LocalPythonTerminalConfig, …)
│   ├── factories.py         # MT5LiveDataClientFactory, MT5LiveExecClientFactory
│   ├── data.py              # MetaTrader5DataClient
│   ├── execution.py         # MetaTrader5ExecutionClient
│   ├── providers.py         # MetaTrader5InstrumentProvider
│   ├── venue_profile.py     # VenueProfile, TICKMILL_DEMO_PROFILE
│   ├── client/              # Low-level MetaTrader5Client (connection, market data, orders)
│   ├── metatrader5/         # RPyC client wrapper + LocalPythonMT5
│   └── parsing/             # MT5 → Nautilus instrument/execution parsers
├── examples/
│   ├── connect_with_external_rpyc.py
│   ├── connect_with_terminal.py
│   ├── capture_symbol_info_fixtures.py  # Capture real MT5 payloads for test fixtures
│   ├── .env.example
│   └── …
├── tests/
│   ├── unit/                # Deterministic logic tests (no external deps)
│   ├── integration/         # MetaTrader5Client tests via fake RPyC bridge
│   ├── integration_tests/   # Full factory-stack integration tests
│   ├── contracts/           # Architectural invariant tests
│   ├── acceptance/          # Live Tier-2 tests (@pytest.mark.live, manual only)
│   ├── performance/         # Hot-path benchmarks
│   ├── memory/              # Memory-stability tests
│   ├── support/             # Fake bridge, harnesses, shared helpers
│   └── test_data/           # Real MT5 API payloads (JSON fixtures for unit tests)
├── MQL5/                    # MQL5 scripts and EA module
├── docs/                    # Architecture and testing contracts, capability matrices
├── pyproject.toml           # Project configuration
├── uv.lock                  # Dependency lock file
├── LICENSE
└── README.md
```

## Project documentation 📚

Before contributing or assigning AI-agent tasks, start with [`docs/index.md`](docs/index.md).

It provides the documentation map for architecture contracts, terminal access rules, testing expectations, capability matrices, project decisions, operational live validation, and AI-agent task guidance.

## Contributing 🤝

Contributions are welcome! Please open an issue or submit a pull request for any enhancements or bug fixes. 🐛

1. Fork the repository. 🍴
2. Create a new branch:
   ```sh
   git checkout -b feature-branch
   ```
3. Make your changes. ✏️
4. Commit your changes:
   ```sh
   git commit -m 'Add some feature'
   ```
5. Push to the branch:
   ```sh
   git push origin feature-branch
   ```
6. Open a pull request. 📥

## License 📄

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Credits 🙏

The first version of this project was based on a fork of a mirror of the original QuantsPub `nautilus_mt5` project.

- Original project: [QuantsPub/nautilus_mt5](https://github.com/quantspub/nautilus_mt5) — no longer available
- Public mirror used as reference: [webclinic017/nautilus_mt5](https://github.com/webclinic017/nautilus_mt5)

Other resources:

- [PyTrader Python MT4/MT5 Trading API Connector](https://github.com/TheSnowGuru/PyTrader-python-mt4-mt5-trading-api-connector-drag-n-drop) 🌟
- [MQL5 Articles](https://www.mql5.com/en/articles/234) 📚
- [MQL5 Forum](https://www.mql5.com/en/forum/244840) 💬