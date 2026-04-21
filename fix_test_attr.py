import re

with open("tests/test_transform.py", "r") as f:
    content = f.read()

# In LiveExecutionClient (base class), the property `account_id` fetches from `_account_id`.
# The code is probably reading `self.account_id`, which fails if base `__init__` isn't called.
# Let's mock the `account_id` property itself on the instance.

new_mock = """
    exec_client = MetaTrader5ExecutionClient.__new__(MetaTrader5ExecutionClient)
    exec_client._instrument_provider = provider_mock
    # Mock property
    type(exec_client).account_id = MagicMock()
    exec_client.account_id.get_id.return_value = "12345"
"""
content = re.sub(
    r'    exec_client = MetaTrader5ExecutionClient\.__new__\(MetaTrader5ExecutionClient\)\n    exec_client\._instrument_provider = provider_mock\n    exec_client\._account_id = MagicMock\(\)\n    exec_client\._account_id\.get_id\.return_value = "12345"',
    new_mock,
    content
)

with open("tests/test_transform.py", "w") as f:
    f.write(content)
