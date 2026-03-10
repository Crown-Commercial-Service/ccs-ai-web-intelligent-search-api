# evaluation script to quantify the performance of WIS with a given configuration and prompt
import os

# Configure Azure Search environment variables BEFORE imports
os.environ["AZURESEARCH_FIELDS_CONTENT_VECTOR"] = "text_vector"
os.environ["AZURESEARCH_FIELDS_CONTENT"] = "chunk"

import argparse
import asyncio
import time
import pandas as pd
import mlflow
from pathlib import Path
from dotenv import load_dotenv
from openai import (
    AsyncAzureOpenAI,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

# LangChain and LangGraph imports
from langchain_community.vectorstores.azuresearch import AzureSearch
from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI
from ccs_ai_josh.multiturn_utils import build_graph, answer_once
from ccs_ai_josh.eval_utils import score_correctness
from langgraph.checkpoint.memory import MemorySaver

# Pydantic AI and other imports
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from wis.ai_docs_filterer_for_RAG import run_rm_labeller
from wis.ccs_website_data import fetch_all_ccs_frameworks
from wis.parallel_eval_utils import (
    is_token_or_rate_limit_error,
    with_exponential_backoff,
)

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
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=10,
        help="Maximum number of truthset rows to process in parallel.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Maximum retries for retryable API errors.",
    )
    parser.add_argument(
        "--initial-backoff-seconds",
        type=float,
        default=1.0,
        help="Initial retry backoff in seconds.",
    )
    parser.add_argument(
        "--max-backoff-seconds",
        type=float,
        default=30.0,
        help="Maximum retry backoff in seconds.",
    )
    return parser.parse_args()


async def run_eval_loop(args):
    retryable_exception_types = (
        RateLimitError,
        APITimeoutError,
        APIConnectionError,
        InternalServerError,
    )

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
    truthset = truthset.reset_index(drop=True)

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

        n_rows = len(truthset)
        responses = [None] * n_rows
        rm_labels = [None] * n_rows
        correctness_scores = [None] * n_rows
        correctness_reasoning = [None] * n_rows
        eval_errors = [None] * n_rows

        labeller_prompt_path = Path(args.labeller_prompt).resolve()
        reasoning_prompt_path = Path(args.reasoning_prompt).resolve()

        semaphore = asyncio.Semaphore(max(1, args.max_concurrency))
        start_time = time.perf_counter()
        completed = 0
        token_limit_rejection_count = 0
        failed_row_count = 0

        async def evaluate_row(row_idx: int, row):
            nonlocal token_limit_rejection_count, failed_row_count
            query = row["Question"]
            expected_answer = row["Expected Answer"]

            async with semaphore:
                try:
                    # Build graph each time to clear context.
                    memory = MemorySaver()
                    graph = build_graph(
                        llm=llm,
                        vector_store=vector_store,
                        checkpointer=memory,
                        prompt_path=reasoning_prompt_path,
                    )

                    rm_label_result = await with_exponential_backoff(
                        op_name="run_rm_labeller",
                        row_idx=row_idx,
                        operation=lambda: run_rm_labeller(
                            pydantic_rm_labeller_model,
                            rm_descriptions,
                            query,
                            prompt_path=labeller_prompt_path,
                        ),
                        max_retries=args.max_retries,
                        initial_backoff_seconds=args.initial_backoff_seconds,
                        max_backoff_seconds=args.max_backoff_seconds,
                        retryable_exception_types=retryable_exception_types,
                    )

                    config = {"configurable": {"rm_filter": rm_label_result.rm_number}}
                    response = await with_exponential_backoff(
                        op_name="answer_once",
                        row_idx=row_idx,
                        operation=lambda: asyncio.to_thread(
                            answer_once, graph, query, config=config
                        ),
                        max_retries=args.max_retries,
                        initial_backoff_seconds=args.initial_backoff_seconds,
                        max_backoff_seconds=args.max_backoff_seconds,
                        retryable_exception_types=retryable_exception_types,
                    )

                    score = None
                    score_reasoning = None
                    if pd.notna(expected_answer) and str(expected_answer).strip():
                        score_dict = await with_exponential_backoff(
                            op_name="score_correctness",
                            row_idx=row_idx,
                            operation=lambda: asyncio.to_thread(
                                score_correctness,
                                llm=llm,
                                question=query,
                                generated_answer=response["answer"],
                                reference_answer=expected_answer,
                            ),
                            max_retries=args.max_retries,
                            initial_backoff_seconds=args.initial_backoff_seconds,
                            max_backoff_seconds=args.max_backoff_seconds,
                            retryable_exception_types=retryable_exception_types,
                        )
                        score = score_dict["score"]
                        score_reasoning = score_dict["reasoning"]

                    return {
                        "row_idx": row_idx,
                        "rm_label_result": rm_label_result,
                        "response": response,
                        "score": score,
                        "score_reasoning": score_reasoning,
                        "error": None,
                    }
                except Exception as error:
                    error_text = str(error)
                    if is_token_or_rate_limit_error(error):
                        token_limit_rejection_count += 1
                    failed_row_count += 1
                    print(
                        f"Error evaluating row {row_idx}. "
                        f"Question: {query!r}. Error: {error_text}"
                    )
                    return {
                        "row_idx": row_idx,
                        "rm_label_result": None,
                        "response": None,
                        "score": None,
                        "score_reasoning": None,
                        "error": error_text,
                    }

        tasks = [
            asyncio.create_task(evaluate_row(row_idx=i, row=row))
            for i, row in truthset.iterrows()
        ]
        for done in asyncio.as_completed(tasks):
            result = await done
            row_idx = result["row_idx"]
            rm_labels[row_idx] = result["rm_label_result"]
            responses[row_idx] = result["response"]
            correctness_scores[row_idx] = result["score"]
            correctness_reasoning[row_idx] = result["score_reasoning"]
            eval_errors[row_idx] = result["error"]

            completed += 1
            if completed % 10 == 0 or completed == n_rows:
                print(f"Processed {completed}/{n_rows} questions")

        elapsed_seconds = time.perf_counter() - start_time
        print(f"Parallel evaluation completed in {elapsed_seconds:.2f} seconds")

        truthset["RM Number Result"] = [
            r.rm_number if r is not None else None for r in rm_labels
        ]
        truthset["RM Number Reasoning"] = [
            r.reasoning if r is not None else None for r in rm_labels
        ]
        truthset["Answer"] = [r["answer"] if r is not None else None for r in responses]
        truthset["Retrieved Files"] = [
            r["source_names"] if r is not None else None for r in responses
        ]
        truthset["Retrieved Contents"] = [
            r["source_contents"] if r is not None else None for r in responses
        ]
        truthset["Correctness Score"] = correctness_scores
        truthset["Correctness Reasoning"] = correctness_reasoning
        truthset["Evaluation Error"] = eval_errors

        # Calculate accuracy
        valid_rm_rows = truthset["RM Number Result"].notna()
        valid_rm_total = valid_rm_rows.sum()
        if valid_rm_total > 0:
            correct = (
                truthset.loc[valid_rm_rows, "RM Number Result"]
                == truthset.loc[valid_rm_rows, "Expected Framework"]
            ).sum()
            accuracy = correct / valid_rm_total
        else:
            accuracy = 0.0
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
        mlflow.log_metric("evaluation_duration_seconds", elapsed_seconds)
        mlflow.log_metric("evaluation_max_concurrency", args.max_concurrency)
        mlflow.log_metric("evaluation_failed_rows", failed_row_count)
        mlflow.log_metric(
            "token_or_rate_limit_rejection_rows", token_limit_rejection_count
        )

        # Save and log results artifact
        outpath = os.path.join("data", "results.tsv")
        truthset.to_csv(outpath, sep="\t", index=False)
        mlflow.log_artifact(outpath)
        print(f"Results written to {outpath} and logged to MLFlow")


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_eval_loop(args))
