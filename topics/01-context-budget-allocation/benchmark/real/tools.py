from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from benchmark.real.artifacts import canonical_json, sha256_text
from benchmark.real.http import PublicAPIClient, github_url, pypi_url

TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "github_get_issue",
        "description": "Get one public GitHub issue or pull request by number.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "owner/repository"},
                "issue_number": {"type": "integer", "minimum": 1},
            },
            "required": ["repo", "issue_number"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "github_list_commits",
        "description": "List recent public commits for a repository or ref.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "sha": {"type": ["string", "null"]},
                "per_page": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["repo", "sha", "per_page"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "github_get_repository_tree",
        "description": "Get a recursive public Git tree at an immutable revision.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"repo": {"type": "string"}, "sha": {"type": "string"}},
            "required": ["repo", "sha"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "github_get_release",
        "description": "Get the latest public GitHub release metadata.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"repo": {"type": "string"}},
            "required": ["repo"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "pypi_get_project",
        "description": "Get current public PyPI project metadata.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"project": {"type": "string"}},
            "required": ["project"],
            "additionalProperties": False,
        },
    },
]


@dataclass
class ToolExecution:
    name: str
    arguments: dict[str, Any]
    output: Any
    cache_key: str
    replayed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def cache_key(name: str, arguments: dict[str, Any]) -> str:
    return sha256_text(f"{name}\n{canonical_json(arguments)}")


def _repo(value: str) -> str:
    parts = value.split("/")
    if len(parts) != 2 or not all(
        p.replace("-", "").replace("_", "").isalnum() for p in parts
    ):
        raise ValueError("repo must be owner/name")
    return value


class ToolExecutor:
    """Executes unique calls live and deterministically replays identical calls."""

    def __init__(
        self,
        client: PublicAPIClient,
        cache: dict[str, Any] | None = None,
        live: bool = False,
    ):
        self.client = client
        self.cache = cache if cache is not None else {}
        self.live = live
        self.executions: list[ToolExecution] = []

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolExecution:
        normalized = self._normalize_args(name, arguments)
        key = cache_key(name, normalized)
        replayed = key in self.cache
        if replayed:
            output = self.cache[key]
        else:
            if not self.live:
                raise RuntimeError(
                    f"no frozen result for {name}; rerun capture with --live"
                )
            output = self._handlers()[name](normalized)
            self.cache[key] = output
        result = ToolExecution(name, normalized, output, key, replayed)
        self.executions.append(result)
        return result

    @property
    def duplicate_count(self) -> int:
        return sum(1 for item in self.executions if item.replayed)

    def _handlers(self) -> dict[str, Callable[[dict[str, Any]], Any]]:
        return {
            "github_get_issue": self._github_get_issue,
            "github_list_commits": self._github_list_commits,
            "github_get_repository_tree": self._github_get_repository_tree,
            "github_get_release": self._github_get_release,
            "pypi_get_project": self._pypi_get_project,
        }

    def _normalize_args(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in self._handlers():
            raise ValueError(f"unknown tool {name!r}")
        if name == "github_get_issue":
            return {
                "repo": _repo(str(args["repo"])),
                "issue_number": int(args["issue_number"]),
            }
        if name == "github_list_commits":
            return {
                "repo": _repo(str(args["repo"])),
                "sha": str(args["sha"]) if args.get("sha") else None,
                "per_page": max(1, min(100, int(args.get("per_page", 30)))),
            }
        if name == "github_get_repository_tree":
            return {"repo": _repo(str(args["repo"])), "sha": str(args["sha"])}
        if name == "github_get_release":
            return {"repo": _repo(str(args["repo"]))}
        return {"project": str(args["project"]).strip().lower()}

    def _github_get_issue(self, args: dict[str, Any]) -> dict[str, Any]:
        result = self.client.get(
            github_url(f"repos/{args['repo']}/issues/{args['issue_number']}")
        )
        body = result.body
        return {
            "source_url": result.url,
            "captured_at": result.captured_at,
            "sha256": result.sha256,
            "repo": args["repo"],
            "number": body["number"],
            "title": body["title"],
            "state": body["state"],
            "body": body.get("body") or "",
            "comments": body.get("comments", 0),
            "created_at": body.get("created_at"),
            "closed_at": body.get("closed_at"),
            "is_pull_request": "pull_request" in body,
        }

    def _github_list_commits(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        query = {"per_page": args["per_page"]}
        if args["sha"]:
            query["sha"] = args["sha"]
        body = self.client.get(
            github_url(f"repos/{args['repo']}/commits", **query)
        ).body
        return [
            {
                "repo": args["repo"],
                "sha": item["sha"],
                "message": item.get("commit", {}).get("message", ""),
                "date": item.get("commit", {}).get("author", {}).get("date"),
                "url": item.get("html_url"),
            }
            for item in body
        ]

    def _github_get_repository_tree(self, args: dict[str, Any]) -> dict[str, Any]:
        result = self.client.get(
            github_url(f"repos/{args['repo']}/git/trees/{args['sha']}", recursive="1")
        )
        body = result.body
        return {
            "repo": args["repo"],
            "revision": args["sha"],
            "source_url": result.url,
            "captured_at": result.captured_at,
            "sha256": result.sha256,
            "truncated": bool(body.get("truncated", False)),
            "tree": [
                {
                    key: item.get(key)
                    for key in ("path", "mode", "type", "sha", "size", "url")
                }
                for item in body.get("tree", [])
            ],
        }

    def _github_get_release(self, args: dict[str, Any]) -> dict[str, Any]:
        result = self.client.get(github_url(f"repos/{args['repo']}/releases/latest"))
        body = result.body
        return {
            "repo": args["repo"],
            "source_url": result.url,
            "captured_at": result.captured_at,
            "sha256": result.sha256,
            "tag_name": body.get("tag_name"),
            "name": body.get("name"),
            "published_at": body.get("published_at"),
            "body": body.get("body") or "",
        }

    def _pypi_get_project(self, args: dict[str, Any]) -> dict[str, Any]:
        result = self.client.get(pypi_url(args["project"]))
        info = result.body["info"]
        return {
            "project": args["project"],
            "source_url": result.url,
            "captured_at": result.captured_at,
            "sha256": result.sha256,
            "name": info.get("name"),
            "version": info.get("version"),
            "summary": info.get("summary"),
            "requires_python": info.get("requires_python"),
            "project_urls": info.get("project_urls") or {},
        }
