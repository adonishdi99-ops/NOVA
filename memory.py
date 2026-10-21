

conversation_history = []

def remember(role, content):
    """Add a message to conversation history."""
    conversation_history.append({"role": role, "content": content})

def recall():
    """Return full conversation history."""
    return conversation_history

def forget():
    """Clear conversation history."""
    conversation_history.clear()