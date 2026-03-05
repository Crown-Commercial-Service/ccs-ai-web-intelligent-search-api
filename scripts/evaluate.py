# evaluation script to quantify the performance of WIS with a given configuration and prompt
import os

# Configure Azure Search environment variables BEFORE imports
os.environ["AZURESEARCH_FIELDS_CONTENT_VECTOR"] = "text_vector"
os.environ["AZURESEARCH_FIELDS_CONTENT"] = "chunk"

import argparse
import asyncio
import pandas as pd
import mlflow
from pathlib import Path
from dotenv import load_dotenv

# LangChain and LangGraph imports
from langchain_community.vectorstores.azuresearch import AzureSearch
from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI
from ccs_ai_josh.multiturn_utils import build_graph, answer_once
from ccs_ai_josh.eval_utils import score_correctness
from langgraph.checkpoint.memory import MemorySaver

# Pydantic AI and other imports
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from openai import AsyncAzureOpenAI
from wis.ai_docs_filterer_for_RAG import run_rm_labeller
from wis.ccs_website_data import fetch_all_ccs_frameworks

load_dotenv()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evaluate WIS performance and track with MLFlow."
    )
    parser.add_argument(
        "--labeller-prompt",
        type=str,
        default="prompts/framework_labeller.md",
        help="Path to the framework labeller prompt markdown file.",
    )
    parser.add_argument(
        "--reasoning-prompt",
        type=str,
        default="prompts/reasoning.md",
        help="Path to the reasoning prompt markdown file.",
    )
    parser.add_argument(
        "--temperature", type=float, default=0.0, help="LLM temperature for evaluation."
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=None,
        help="Number of samples from truthset to evaluate (default: all).",
    )
    return parser.parse_args()


async def run_eval_loop(args):
    # MLFlow setup
    mlflow_tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow_experiment_name = os.getenv(
        "MLFLOW_EXPERIMENT_NAME", "WIS-Prompt-Optimization"
    )

    mlflow.set_tracking_uri(mlflow_tracking_uri)
    mlflow.set_experiment(mlflow_experiment_name)

    # Initialize models and resources
    embeddings = AzureOpenAIEmbeddings(
        azure_deployment=os.getenv("EMBEDDING_MODEL_NAME"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        azure_endpoint=os.getenv("EMBEDDING_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_KEY"),
    )

    vector_store = AzureSearch(
        azure_search_endpoint=os.getenv("VECTOR_STORE_ENDPOINT"),
        azure_search_key=os.getenv("VECTOR_STORE_KEY"),
        index_name=os.getenv("VECTOR_STORE_INDEX"),
        embedding_function=embeddings.embed_query,
        content_key="chunk",
    )

    llm = AzureChatOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_KEY"),
        azure_deployment=os.getenv("DEPLOYMENT_NAME"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        temperature=args.temperature,
    )

    pydantic_azure_client = AsyncAzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_KEY"),
        azure_deployment=os.getenv("DEPLOYMENT_NAME"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    )
    pydantic_rm_labeller_model = OpenAIChatModel(
        model_name=os.getenv("DEPLOYMENT_NAME"),
        provider=OpenAIProvider(openai_client=pydantic_azure_client),
    )

    ccs_frameworks = fetch_all_ccs_frameworks()
    rm_descriptions = "\n".join(
        [
            f"RM: {r.rm_number} | "
            f"Keywords: {r.keywords if 'keywords' in r and str(r.keywords).strip() else 'N/A'} | "
            f"Summary: {r.summary} | "
            f"Pillar: {r.pillar} ({r.category})"
            for _, r in ccs_frameworks.iterrows()
        ]
    )

    # Load truthset
    truthset_file_path = os.path.join("data", "truthset.tsv")
    truthset = pd.read_csv(truthset_file_path, delimiter="\t")

    if args.num_samples:
        truthset = truthset.head(args.num_samples)

    print(f"Evaluating {len(truthset)} samples...")

    with mlflow.start_run():
        # Log parameters
        mlflow.log_param("labeller_prompt_path", args.labeller_prompt)
        mlflow.log_param("reasoning_prompt_path", args.reasoning_prompt)
        mlflow.log_param("temperature", args.temperature)
        mlflow.log_param("model_deployment", os.getenv("DEPLOYMENT_NAME"))
        mlflow.log_param("num_samples", len(truthset))

        # Log prompt contents as artifacts for direct viewing in MLFlow UI
        mlflow.log_artifact(args.labeller_prompt, "prompts")
        mlflow.log_artifact(args.reasoning_prompt, "prompts")

        responses = []
        rm_labels = []
        correctness_scores = []
        correctness_reasoning = []

        labeller_prompt_path = Path(args.labeller_prompt).resolve()
        reasoning_prompt_path = Path(args.reasoning_prompt).resolve()

        for i, row in truthset.iterrows():
            query = row["Question"]
            expected_answer = row["Expected Answer"]

            # build the graph each time, to clear context
            memory = MemorySaver()
            graph = build_graph(
                llm=llm,
                vector_store=vector_store,
                checkpointer=memory,
                prompt_path=reasoning_prompt_path,
            )

            rm_label_result = await run_rm_labeller(
                pydantic_rm_labeller_model,
                rm_descriptions,
                query,
                prompt_path=labeller_prompt_path,
            )
            rm_labels.append(rm_label_result)

            config = {"configurable": {"rm_filter": rm_label_result.rm_number}}
            response = answer_once(graph, query, config=config)
            responses.append(response)

            # Score correctness if a reference answer is provided
            if pd.notna(expected_answer) and str(expected_answer).strip():
                try:
                    score_dict = score_correctness(
                        llm=llm,
                        question=query,
                        generated_answer=response["answer"],
                        reference_answer=expected_answer,
                    )
                    correctness_scores.append(score_dict["score"])
                    correctness_reasoning.append(score_dict["reasoning"])
                except Exception as e:
                    print(f"Error scoring correctness for query {i}: {e}")
                    correctness_scores.append(None)
                    correctness_reasoning.append(None)
            else:
                correctness_scores.append(None)
                correctness_reasoning.append(None)

            if (i + 1) % 10 == 0:
                print(f"Processed {i + 1}/{len(truthset)} questions")

        truthset["RM Number Result"] = [i.rm_number for i in rm_labels]
        truthset["RM Number Reasoning"] = [i.reasoning for i in rm_labels]
        truthset["Answer"] = [i["answer"] for i in responses]
        truthset["Retrieved Files"] = [i["source_names"] for i in responses]
        truthset["Retrieved Contents"] = [i["source_contents"] for i in responses]
        truthset["Correctness Score"] = correctness_scores
        truthset["Correctness Reasoning"] = correctness_reasoning

        # Calculate accuracy
        correct = (truthset["RM Number Result"] == truthset["Expected Framework"]).sum()
        accuracy = correct / len(truthset)
        print(f"Accuracy: {accuracy:.4f}")

        # Calculate correctness metrics
        valid_scores = [s for s in correctness_scores if s is not None]
        if valid_scores:
            pct_perfect = len([s for s in valid_scores if s == "PERFECT"]) / len(
                valid_scores
            )
            pct_correct_or_better = len(
                [s for s in valid_scores if s in ("PERFECT", "CORRECT")]
            ) / len(valid_scores)
        else:
            pct_perfect = 0
            pct_correct_or_better = 0

        print(f"Perfect Answers: {pct_perfect:.4%}")
        print(f"Perfect or Correct Answers: {pct_correct_or_better:.4%}")

        # Log metrics
        mlflow.log_metric("RM labelling accuracy", accuracy)
        mlflow.log_metric("Percentage of Answers Perfect", pct_perfect)
        mlflow.log_metric(
            "Percentage of Answers Perfect or Correct", pct_correct_or_better
        )

        # Save and log results artifact
        outpath = os.path.join("data", "results.tsv")
        truthset.to_csv(outpath, sep="\t", index=False)
        mlflow.log_artifact(outpath)
        print(f"Results written to {outpath} and logged to MLFlow")


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_eval_loop(args))
