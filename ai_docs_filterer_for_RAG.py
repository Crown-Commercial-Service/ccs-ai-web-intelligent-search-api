from pydantic import BaseModel, Field
from pydantic_ai import Agent
from ccs_website_data import  fetch_all_ccs_frameworks

#Fetching data is be done once on loading of api
# ccs_frameworks = fetch_all_ccs_frameworks()
# ccs_frameworks = ccs_frameworks[0:2]
# # If description exists and isn't empty, use it; otherwise, use category
# rm_descriptions = "\n".join([
#     f"{r.rm_number}: {r.description if r.description and str(r.description).strip() else r.category}"
#     for _, r in ccs_frameworks.iterrows()
# ])
# print(rm_descriptions)


class DataFilterer(BaseModel):
    rm_number: str = Field(description="The extracted or inferred RM number.")
    reasoning: str = Field(description="Briefly why you picked this RM.")

async def run_rm_labeller(model, rm_descriptions, user_input):
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



