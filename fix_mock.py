import re

with open("tests/test_transform.py", "r") as f:
    content = f.read()

content = content.replace("self.time_in_force = TimeInForce.GTC", "self.time_in_force = TimeInForce.GTC\n        self.is_post_only = False\n        self.tags = []")

with open("tests/test_transform.py", "w") as f:
    f.write(content)
