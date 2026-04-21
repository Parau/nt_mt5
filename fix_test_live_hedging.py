import re

with open("tests/test_live_hedging.py", "r") as f:
    content = f.read()

# Looks like test_live_hedging.py has some hardcoded timeout failure or it's trying to connect to MT5 locally which doesn't exist in the CI/runner environment.
# Let's just mock or ignore it as a smoke test that fails when there's no MT5. The user instruction said: "live smoke tests run against their actual MT5 environment".
# Wait, the ngrok RPyC environment might not be running or the test is timing out waiting for quotes because it's the weekend or market is closed.
# The user explicitely said "live smoke tests run against their actual MT5 environment."
# Let's check `test_live_acceptance.py`.
pass
