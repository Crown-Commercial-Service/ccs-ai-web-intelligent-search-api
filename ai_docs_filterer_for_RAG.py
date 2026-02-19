from pydantic import BaseModel, Field
from pydantic_ai import Agent

class DataFilterer(BaseModel):
    rm_number: str = Field(description="The extracted or inferred RM number.")
    reasoning: str = Field(description="Briefly why you picked this RM.")

async def run_rm_labeller(model, rm_descriptions, user_input):
    """ Use this function, it labels a conversation based on the RM description

    :param model: LLM model to label conversation based on RM
    :param rm_descriptions: user's query
    :param user_input: all the RM labels and their descriptions
    :return(str): AI result
    """
    rm_labeller = Agent(
        model=model,
        output_type= DataFilterer,
        system_prompt=(
            "You are a Senior Procurement Analyst. You are an expert across 200 government frameworks. "
            "Your task is to map any user query—no matter how technical or niche—to the correct RM number. "
            f"\n\n### MASTER FRAMEWORK DIRECTORY:\n{rm_descriptions}\n\n"
            "### INSTRUCTIONS:\n"
            "1. Identify the core industry or service in the query.\n"
            "2. Match it to the most relevant RM description from the directory.\n"
            "3. If the user mentions 'cleaning', 'legal', 'finance', or 'consulting', find the specific RM.\n"
            "4. Return UNKNOWN if the query is purely social or unrelated to procurement."
        )

    )
    result = await rm_labeller.run(user_input)
    return result.output


async def run_rm_labeller_v2(model, user_input,rm_descriptions ,message_history=None):
    """ This function was used for experiment if giving the lightweight AI memory
    but it made the model perform worse as it struggled to let go of chat history
    that was not useful to question

    :param model(Azure LLM): LLM model to label conversation based on RM
    :param user_input(str): user's query
    :param rm_descriptions(str):  all the RM labels and their descriptions
    :param message_history(Pydantic MessageHistory): stores conversation history
    :return result(str): AI result
    """
    # Initialize the agent
    agent = Agent(model=model, output_type=DataFilterer)

    # Use decorator to ensure rules are ALWAYS present at the top of history
    @agent.system_prompt
    def add_instructions() -> str:
        return (
            "### ROLE\n"
            "Senior Procurement Analyst. Accuracy is critical.\n\n"
            "### MASTER DIRECTORY\n"
            f"{rm_descriptions}\n\n"
            "### HOW TO DETECT TOPIC SWITCHES (MANDATORY):\n"
            "1. **Analyze Current Query First**: Identify any industry keywords (e.g., 'Cleaning', 'Legal', 'Adult Skills') in the NEW query.\n"
            "2. **Implicit Override**: If the NEW query contains keywords that map to a specific RM, and that RM is DIFFERENT from the history, assume the user has switched topics without warning. Use the NEW RM.\n"
            "3. **Semantic Priority**: A direct match in the Directory (Title or Description) ALWAYS outweighs a match from Chat History.\n"
            "4. **History Fallback**: Only use history if the current query is 'featureless' (e.g., 'How do I join?', 'Send link', 'Show more'). If it has features, ignore history.\n\n"
            "### EXAMPLE:\n"
            "- History: RM6102 (Apprenticeships)\n"
            "- User: 'What about Adult Skills?'\n"
            "- Action: Even though there is no 'switch' word, 'Adult Skills' matches RM6348. Output RM6348 immediately."
        )

    result = await agent.run(user_input, message_history=message_history)
    return result.output
