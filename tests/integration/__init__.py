"""
tests/integration/
==================
Low-level integration tests for the MetaTrader5Client layer.

These tests exercise MetaTrader5Client directly against the fake RPyC bridge
(tests/support/fake_mt5_rpyc_bridge.py), bypassing the high-level
DataClient / ExecutionClient / Factory stack.

Layer tested
------------
    fake RPyC bridge → MetaTrader5Client

This is one layer below the canonical NautilusTrader adapter integration tests,
which live in tests/integration_tests/adapters/mt5/ and test the full path:

    fake RPyC bridge → MetaTrader5Client
                     → MetaTrader5DataClient / MetaTrader5ExecutionClient
                     → Factory

When to add tests here vs. tests/integration_tests/adapters/mt5/
-----------------------------------------------------------------
- Add here when the behaviour under test is specific to MetaTrader5Client
  internals (connection lifecycle, retcode handling, retry logic, raw RPyC
  call translation) and does not require the high-level adapter stack.
- Add to tests/integration_tests/adapters/mt5/ when the behaviour is
  observable through the public DataClient / ExecutionClient / Factory API
  (order events, instrument loading, factory wiring, config validation).
"""
