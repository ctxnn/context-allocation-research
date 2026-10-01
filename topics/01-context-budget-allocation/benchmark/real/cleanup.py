from __future__ import annotations

import argparse

from benchmark.real.artifacts import read_json
from benchmark.real.constants import RESOURCE_PATH
from benchmark.real.openai_api import OpenAIBackend


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicitly delete Benchmark 2 OpenAI resources"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="required acknowledgement for destructive API calls",
    )
    parser.add_argument("--vector-store-id", required=True)
    parser.add_argument(
        "--keep-files", action="store_true", help="delete only the vector store"
    )
    args = parser.parse_args()
    if not args.live:
        raise SystemExit("cleanup deletes remote resources; pass --live")
    if not args.vector_store_id.startswith("vs_"):
        raise SystemExit("vector store id must start with vs_")

    file_ids = []
    if RESOURCE_PATH.exists():
        resources = read_json(RESOURCE_PATH)
        if resources.get("vector_store_id") == args.vector_store_id:
            file_ids = list(resources.get("file_ids", []))
    backend = OpenAIBackend()
    deleted = backend.delete_vector_store(args.vector_store_id)
    print(f"vector store {args.vector_store_id}: deleted={deleted}")
    if not args.keep_files:
        for file_id in file_ids:
            print(f"file {file_id}: deleted={backend.delete_file(file_id)}")
    if deleted and not args.keep_files and RESOURCE_PATH.exists():
        resources = read_json(RESOURCE_PATH)
        if resources.get("vector_store_id") == args.vector_store_id:
            RESOURCE_PATH.unlink()
            print(f"removed local resource checkpoint {RESOURCE_PATH}")


if __name__ == "__main__":
    main()
