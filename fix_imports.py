import re

with open("nautilus_mt5/data.py", "r") as f:
    content = f.read()

content = content.replace("from nautilus_trader.live.messages import", "from nautilus_trader.data.messages import")

with open("nautilus_mt5/data.py", "w") as f:
    f.write(content)

with open("nautilus_mt5/execution.py", "r") as f:
    content = f.read()

# Make sure execution client uses execution.messages
content = content.replace("from nautilus_trader.live.messages import", "from nautilus_trader.execution.messages import")

with open("nautilus_mt5/execution.py", "w") as f:
    f.write(content)
