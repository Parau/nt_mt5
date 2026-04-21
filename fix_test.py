import re
with open("tests/test_transform.py", "r") as f:
    content = f.read()

content = content.replace("mt5_order.volume == 100.0", "mt5_order.volume_initial == 100.0")

with open("tests/test_transform.py", "w") as f:
    f.write(content)
