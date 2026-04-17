import re

with open("nautilus_mt5/metatrader5/config.py", "r") as f:
    content = f.read()

# Remove the __init__ methods from the msgspec Structs
content = re.sub(r'    def __init__\(self.*?\):\n(?:        self\..*?\n)*', '', content, flags=re.MULTILINE)

with open("nautilus_mt5/metatrader5/config.py", "w") as f:
    f.write(content)
