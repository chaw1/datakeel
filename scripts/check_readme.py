# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute the documented local quick-start commands in a fresh workspace."""

import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import ClientTransport, StdioTransport
from pydantic import Field, HttpUrl
from rich.console import Console

from datakeel.core.ask_models import AskAnswer
from datakeel.core.catalog_models import ImpactResult
from datakeel.core.metric_models import MetricCard
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.ontology.models import FunctionResult
from datakeel.ontology.tool_models import ToolOutcome

ROOT = Path(__file__).resolve().parents[1]


class CommandServer(BoundaryModel):
    """Validate a complete local MCP process configuration from the README."""

    command: str
    args: list[str]
    env: dict[str, str]


class SseServer(BoundaryModel):
    """Validate an HTTP MCP server configuration without connecting to it."""

    url: HttpUrl


class McpConfiguration(BoundaryModel):
    """Accept only the documented client-server configuration envelope."""

    mcp_servers: dict[str, CommandServer | SseServer] = Field(alias="mcpServers")


def validate_examples() -> CommandServer:
    """Parse both README JSON examples with strict typed MCP boundaries."""
    command = None
    for name in ("README.md", "README.zh.md"):
        content = (ROOT / name).read_text(encoding="utf-8")
        examples = re.findall(r"```json\n(.*?)\n```", content, flags=re.DOTALL)
        if not examples:
            msg = f"No MCP configuration examples found in {name}"
            raise ValueError(msg)
        for example in examples:
            parsed = McpConfiguration.model_validate_json(example)
            for server in parsed.mcp_servers.values():
                if isinstance(server, CommandServer):
                    command = server
    if command is None:
        msg = "README must document a local stdio command"
        raise ValueError(msg)
    return command


def local_environment(directory: Path) -> dict[str, str]:
    """Discard inherited service settings and bind every exercised command to local fixtures."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DATAKEEL_", "AWS_", "OPENAI_", "ANTHROPIC_"))
    }
    environment.update(
        {
            "DATAKEEL_HOME": str(directory),
            "DATAKEEL_DATABASE_URL": f"sqlite:///{directory / 'state.db'}",
            **dict.fromkeys(("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"), ""),
            **dict.fromkeys(("http_proxy", "https_proxy", "all_proxy"), ""),
        }
    )
    return environment


async def verified_read[T: ClientTransport](
    client: Client[T], name: str, arguments: JsonDocument
) -> FunctionResult:
    """Require the real MCP response to carry successful audited asset references."""
    response = await client.call_tool(name, arguments.root)
    result = ToolOutcome.model_validate(response.structured_content)
    if result.status != "SUCCEEDED" or not result.asset_refs:
        msg = f"README MCP command failed its audited read: {name}"
        raise RuntimeError(msg)
    return FunctionResult.model_validate(result.content.root)


async def verified_denial[T: ClientTransport](
    client: Client[T], name: str, arguments: JsonDocument
) -> None:
    """Require an explicit asset refusal with no returned tool data."""
    response = await client.call_tool(name, arguments.root, raise_on_error=False)
    result = ToolOutcome.model_validate(response.structured_content)
    if (
        not response.is_error
        or result.status != "FAILED"
        or result.content.root
        or "apply for access" not in (result.error or "")
        or "requires an active" not in (result.error or "")
    ):
        msg = f"README protected MCP read did not refuse access: {name}"
        raise RuntimeError(msg)


async def verify_enterprise_stdio[T: ClientTransport](client: Client[T]) -> None:
    """Exercise permitted metadata reads and an explicit protected-catalog refusal."""
    result = await verified_read(
        client,
        "ask_data",
        JsonDocument(
            {
                "question": "上个季度华东区零售额是多少",
                "reference_instant": "2026-10-01T00:00:00Z",
            }
        ),
    )
    answer = AskAnswer.model_validate(result.data)
    if answer.status != "answered" or answer.result is None or answer.result.rows != [[4979475]]:
        msg = "README MCP question returned an incorrect enterprise answer"
        raise RuntimeError(msg)
    await verified_denial(client, "list_metrics", JsonDocument({"limit": 2}))
    listed = await verified_read(
        client, "list_metrics", JsonDocument({"limit": 2, "search": "retail_revenue"})
    )
    if [ref.asset_id for ref in listed.asset_refs] != ["retail_revenue"]:
        msg = "README filtered metric list did not retain its exact permitted scope"
        raise RuntimeError(msg)
    explained = await verified_read(
        client, "explain_metric", JsonDocument({"metric_id": "retail_revenue"})
    )
    card = MetricCard.model_validate(explained.data)
    impacted = await verified_read(
        client, "impact_of", JsonDocument({"asset_id": "ecommerce/main/orders/paid_amount"})
    )
    impact = ImpactResult.model_validate(impacted.data)
    if card.definition.id != "retail_revenue" or not impact.objects:
        msg = "README MCP metadata tools returned incomplete enterprise evidence"
        raise RuntimeError(msg)


async def verify_stdio(config: CommandServer, environment: dict[str, str]) -> None:
    """Launch the README command with resolved paths and verify a real MCP exchange."""
    executable = shutil.which("uv")
    if executable is None:
        msg = "Install uv before running README checks"
        raise RuntimeError(msg)
    transport = StdioTransport(
        command=config.command.replace("/absolute/path/to/uv", executable),
        args=[
            argument.replace("/absolute/path/to/datakeel", str(ROOT)) for argument in config.args
        ],
        env=environment,
        keep_alive=False,
        log_file=Path(environment["DATAKEEL_HOME"]) / "mcp.log",
    )
    async with Client(transport, mode="legacy") as client:
        names = {tool.name for tool in await client.list_tools()}
        required = {
            "list_datasets",
            "search_files",
            "query_evidence",
            "get_evidence",
            "explain_sample",
            "quarantine_files",
            "decide_assertions",
            "approve_plan",
            "execute_plan",
            "ask_data",
            "list_metrics",
            "explain_metric",
            "impact_of",
        }
        if not required <= names:
            msg = "README MCP command did not expose the controlled tools"
            raise RuntimeError(msg)
        await verified_read(client, "list_datasets", JsonDocument({}))
        await verify_enterprise_stdio(client)
    Console().print(f"README stdio handshake and audited read passed: {len(names)} tools.")


def run_command(
    arguments: list[str], environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Capture one documented local command without interpreting its failure as success."""
    result = subprocess.run(  # noqa: S603  # Fixed local Python module and argv, never a shell.
        [sys.executable, "-m", "datakeel.cli", *arguments],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    console = Console()
    for output in (result.stdout, result.stderr):
        if output:
            console.print(output, markup=False, highlight=False, soft_wrap=True, end="")
    return result


def verify_denied_command(
    arguments: list[str], environment: dict[str, str], output: Path | None = None
) -> None:
    """Require a nonzero asset authorization failure, no stdout data and no export artifact."""
    result = run_command(arguments, environment)
    if (
        result.returncode == 0
        or result.stdout.strip()
        or "AuthorizationError" not in result.stderr
        or "requires an active" not in result.stderr
        or "apply for access" not in result.stderr
        or (output is not None and output.exists())
    ):
        msg = "README protected command did not fail safely with an asset authorization refusal"
        raise RuntimeError(msg)
    Console().print(f"README protected command refused as expected: {arguments[0]}")


def main() -> None:
    """Validate install-independent demo, export and migration instructions."""
    config = validate_examples()
    with tempfile.TemporaryDirectory(prefix="datakeel-readme-") as temporary:
        environment = local_environment(Path(temporary))
        run_command(["migrate"], environment).check_returncode()
        demo = run_command(["demo", "--once"], environment)
        demo.check_returncode()
        dataset_id = JsonDocument.model_validate_json(demo.stdout).root.get("dataset_id")
        if not isinstance(dataset_id, str) or not dataset_id:
            msg = "README demo did not identify its generated public dataset"
            raise RuntimeError(msg)
        events = Path(temporary) / "events.json"
        verify_denied_command(
            ["export", "--format", "openlineage", "--output", str(events)], environment, events
        )
        verify_denied_command(
            ["ask", "退货率为什么上升", "--reference-instant", "2026-10-01T00:00:00Z"], environment
        )
        for arguments in (
            ["export", "--format", "openlineage", "--dataset", dataset_id, "--output", str(events)],
            ["export", "--format", "croissant", "--output", str(Path(temporary) / "dataset.json")],
            ["eval", "--provider", "fake"],
            ["eval", "--provider", "fake", "--json"],
            ["eval-evidence", "--json"],
            ["rebuild-evidence"],
            ["ask", "上个季度华东区零售额是多少", "--reference-instant", "2026-10-01T00:00:00Z"],
            ["ask", "上个季度营业额是多少", "--reference-instant", "2026-10-01T00:00:00Z"],
            ["eval-ask", "--json"],
            ["rebuild-catalog"],
            ["mcp", "--help"],
        ):
            run_command(arguments, environment).check_returncode()
        asyncio.run(asyncio.wait_for(verify_stdio(config, environment), timeout=30))
        Console().print("Quick start commands passed in a fresh local workspace.")


if __name__ == "__main__":
    main()
