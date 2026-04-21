import re

with open("tests/test_transform.py", "r") as f:
    content = f.read()

# I see the error is coming from `nautilus_pyo3.AccountId(self.account_id.value)`
# because `self.account_id` is a `MagicMock` in my test.
# We should mock `account_id` properly.
new_mock = """
    exec_client = MetaTrader5ExecutionClient.__new__(MetaTrader5ExecutionClient)
    exec_client._instrument_provider = provider_mock

    class MockAccountId:
        def __init__(self, val):
            self.value = val
        def get_id(self):
            return self.value

    exec_client._account_id = MockAccountId("12345")
    type(exec_client).account_id = property(lambda self: self._account_id)
"""
content = re.sub(
    r'    exec_client = MetaTrader5ExecutionClient\.__new__\(MetaTrader5ExecutionClient\)\n    exec_client\._instrument_provider = provider_mock\n    # Mock property\n    type\(exec_client\)\.account_id = MagicMock\(\)\n    exec_client\.account_id\.get_id\.return_value = "12345"',
    new_mock,
    content
)

with open("tests/test_transform.py", "w") as f:
    f.write(content)
