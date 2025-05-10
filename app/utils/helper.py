from typing import Dict
from datetime import datetime
from livekit.agents import function_tool

# In-memory store for orders
orders: Dict[str, Dict[str, str]] = {}

@function_tool
async def place_order(customer_name: str, mode_of_payment: str, delivery_address: str) -> Dict[str, str]:
    """
    Place a new order in the system.

    Args:
        customer_name: The name of the customer placing the order.
        mode_of_payment: Payment mode (e.g., "Cash on Delivery", "UPI", etc.)
        delivery_address: Address for delivery.

    Returns:
        A confirmation message with a unique order ID.
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    order_id = f"{customer_name.lower().replace(' ', '_')}_{timestamp}"

    orders[order_id] = {
        "customer_name": customer_name,
        "mode_of_payment": mode_of_payment,
        "delivery_address": delivery_address,
        "created_at": datetime.utcnow().isoformat()
    }

    return {
        "status": "success",
        "message": f"Order placed for {customer_name} to be delivered at {delivery_address}",
        "order_id": order_id
    }

def list_orders() -> Dict[str, Dict[str, str]]:
    """
    Returns all stored orders.

    Returns:
        A dictionary of all orders keyed by order ID.
    """
    return orders


