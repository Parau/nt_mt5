import re

with open("nautilus_mt5/metatrader5/MetaTrader5.py", "r") as f:
    content = f.read()

# Fix undefined `args` and `kwargs` that appeared in these dummy functions.
content = content.replace("def market_book_release(self,symbol):", "def market_book_release(self,symbol,*args,**kwargs):")
content = content.replace("def order_send(self,request):", "def order_send(self,request,*args,**kwargs):")
content = content.replace("def history_orders_total(self,date_from, date_to):", "def history_orders_total(self,date_from, date_to,*args,**kwargs):")
content = content.replace("def history_deals_total(self,date_from, date_to):", "def history_deals_total(self,date_from, date_to,*args,**kwargs):")


with open("nautilus_mt5/metatrader5/MetaTrader5.py", "w") as f:
    f.write(content)
