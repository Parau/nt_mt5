import re

with open("pyproject.toml", "r") as f:
    content = f.read()

content = content.replace('requires-python = ">=3.11,<3.13"', 'requires-python = ">=3.12,<3.15"')
content = content.replace('target-version = "py311"', 'target-version = "py312"')

with open("pyproject.toml", "w") as f:
    f.write(content)
