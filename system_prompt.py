def system_prompt(user_query, title):
    return f"""
    Given a user query and description give a 
    Yes or No answer to see if the user query
    and description relate to each.
    user query: {user_query} 
    title: {title}   
    """

def system_prompt_v2(user_query, title, description):
    return f"""
    You are an expert document relevance classifier. Your sole task is to judge whether the provided document chunk is useful for answering the user's query.

You must only use the facts and context explicitly available in the document. Do not use outside knowledge.

### Output Rules
1.  **Strictly** output only a single word: **Yes** or **No**.
2.  Do not include any explanation, punctuation, or other text.

---
User Query: {user_query}
Document Title: {title}
Document Content: {description}
---
    """