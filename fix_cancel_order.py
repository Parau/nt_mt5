import re
with open("nautilus_mt5/client/order.py", "r") as f:
    content = f.read()

# Fix cancel_order so it sends a real MT5 Trade Request with TRADE_ACTION_REMOVE
content = re.sub(
    r'def cancel_order\(self, order_id: int, manual_cancel_order_time: str = ""\) -> None:\n.*?self\._log\.warning\("MT5 natively requires a TRADE_ACTION_REMOVE order request\. This method needs to be aligned\."\)',
    r'''def cancel_order(self, order_id: int, manual_cancel_order_time: str = "") -> None:
        """
        Cancel an order through the MT5Client.

        Parameters
        ----------
        order_id : int
            The unique identifier for the order to be canceled (ticket).
        """
        send_method = getattr(self._mt5_client['mt5'], "order_send", None)
        if send_method:
            req = {
                "action": 8, # TRADE_ACTION_REMOVE
                "order": int(order_id),
            }
            res = send_method(req)
            self._log.info(f"MT5 order_send RESULT (CANCEL): {res}")
        else:
            self._log.warning("MT5Client has no method to send cancel orders. (Missing order_send)")''',
    content,
    flags=re.DOTALL
)

with open("nautilus_mt5/client/order.py", "w") as f:
    f.write(content)
