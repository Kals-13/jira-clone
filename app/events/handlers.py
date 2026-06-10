import logging

logger = logging.getLogger("jiralite.notifications")

# A globally toggleable flag to simulate downstream service crashes
SIMULATE_MICROSERVICE_DOWN = False

async def dispatch_email_notification(payload: dict) -> dict:
    """Simulates sending a real-time email or webhook message."""
    if SIMULATE_MICROSERVICE_DOWN:
        logger.error("Network Timeout: Connection refused by notification broker.")
        raise ConnectionError("Notification microservice unavailable")
        
    logger.info(f"Notification sent successfully: {payload.get('title')}")
    return {"status": "delivered"}