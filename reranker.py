from langchain_openai import  AzureChatOpenAI
import os
from system_prompt import system_prompt
from dotenv import load_dotenv
import os


load_dotenv()

llm = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    azure_deployment=os.getenv("DEPLOYMENT_NAME"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    temperature=0.0,
    top_p=1,
    frequency_penalty=0,
    presence_penalty=0,
    seed=0,
    max_tokens=1,
)

def rerank_list(results, user_query):
    """
    solution
    :param results:
    :return:
    """
    good_list = []
    bad_list = []
    for result in results:
        description = result["description"]
        full_text = result["title"] + " " + description
        sys_prompt = system_prompt(user_query, full_text)
        response = llm.invoke(sys_prompt)
        if "Yes" in  response.content:
            good_list.append(result)


        if "No" in response.content:
            bad_list.append(result)

    return good_list  + bad_list
