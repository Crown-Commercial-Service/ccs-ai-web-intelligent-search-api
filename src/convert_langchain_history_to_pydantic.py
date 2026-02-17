from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart


def convert_history_for_pydantic(langchain_messages):
    """Helper to convert CosmosDB messages to PydanticAI format"""
    pydantic_msgs = []
    for m in langchain_messages:
        if m.type == "human":
            pydantic_msgs.append(ModelRequest(parts=[UserPromptPart(content=m.content)]))
        elif m.type == "ai" and m.content:
            pydantic_msgs.append(ModelResponse(parts=[TextPart(content=m.content)]))
    return pydantic_msgs
