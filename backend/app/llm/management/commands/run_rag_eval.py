from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from app.llm.evals.rag_eval import DEFAULT_DATASET_NAME
from app.llm.evals.rag_eval import SAMPLE_DATASET_PATH
from app.llm.evals.rag_eval import langsmith_configured
from app.llm.evals.rag_eval import load_examples
from app.llm.evals.rag_eval import run_rag_evaluation


class Command(BaseCommand):
    help = "Run LangSmith offline evals for the multimodal RAG chat pipeline."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dataset-file",
            type=Path,
            default=SAMPLE_DATASET_PATH,
            help="Path to a JSON file of eval examples (inputs/outputs).",
        )
        parser.add_argument(
            "--dataset-name",
            default=DEFAULT_DATASET_NAME,
            help="LangSmith dataset name when using --sync-dataset.",
        )
        parser.add_argument(
            "--experiment-prefix",
            default="promptly-rag",
            help="Prefix for the LangSmith experiment name.",
        )
        parser.add_argument(
            "--sync-dataset",
            action="store_true",
            help="Upload examples to LangSmith and evaluate from the named dataset.",
        )
        parser.add_argument(
            "--local",
            action="store_true",
            help="Run evals without uploading results to LangSmith.",
        )
        parser.add_argument(
            "--max-concurrency",
            type=int,
            default=1,
            help="Maximum number of concurrent eval runs.",
        )

    def handle(self, *args, **options):
        upload_results = not options["local"]
        if upload_results and not langsmith_configured():
            raise CommandError(
                "Set LANGSMITH_API_KEY in backend/.envs/.local/.rag, "
                "or pass --local to run without uploading.",
            )

        dataset_file: Path = options["dataset_file"]
        if not dataset_file.exists():
            raise CommandError(f"Dataset file not found: {dataset_file}")

        examples = load_examples(dataset_file)
        self.stdout.write(
            self.style.NOTICE(
                f"Running eval on {len(examples)} examples from {dataset_file}",
            ),
        )

        if not examples:
            raise CommandError("Dataset file contains no examples.")

        results = run_rag_evaluation(
            examples=examples,
            dataset_name=options["dataset_name"],
            experiment_prefix=options["experiment_prefix"],
            upload_results=upload_results,
            sync_to_langsmith=options["sync_dataset"],
            max_concurrency=options["max_concurrency"],
        )

        if upload_results:
            self.stdout.write(
                self.style.SUCCESS(
                    "Eval complete. View results at https://smith.langchain.com",
                ),
            )
        else:
            self.stdout.write(self.style.SUCCESS("Local eval complete."))
            # print the results in a readable format
            for i, row in enumerate(results, start=1):
                question = row["example"].inputs["question"]
                answer = (row["run"].outputs or {}).get("answer", "")
                self.stdout.write(f"\nExample {i}: {question}")
                self.stdout.write(f"  Answer: {answer[:200]}{'...' if len(answer) > 200 else ''}")
                for r in row["evaluation_results"]["results"]:
                    score = "N/A" if r.score is None else f"{r.score:.2f}"
                    self.stdout.write(f"  {r.key}: {score}")
