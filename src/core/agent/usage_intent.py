from typing import Optional, Dict, Any

def with_usage_intent(usage: Optional[Dict], intent: str) -> Optional[Dict]:
    """Tag AI usage with an intent label"""
    if not usage:
        return None
    if usage.get("intent"):
        return usage
    return {**usage, "intent": intent}
