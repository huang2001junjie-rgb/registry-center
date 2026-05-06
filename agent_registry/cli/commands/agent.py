"""
Agent Management Commands

Manage agent via internal UDS service.
"""

from argparse import ArgumentParser, Namespace
from typing import Dict

from agent_registry.cli import BaseCommand, CLI, Output
from agent_registry.cli.uds_client import get_uds_client


@CLI.register
class AgentCommand(BaseCommand):
    """Agent management command group"""
    
    @property
    def name(self) -> str:
        return "agent"
    
    @property
    def help_text(self) -> str:
        return "Agent management commands via internal UDS service"
    
    @property
    def subcommands(self) -> Dict[str, BaseCommand]:
        return {
            "approval": ApprovalCommand(),
            "uds-list": UDSListCommand(),
            "uds-get": UDSGetCommand(),
            "add-tags": AddTagsCommand(),
        }
    
    def execute(self, args: Namespace) -> int:
        return 0


class ApprovalCommand(BaseCommand):
    """Approve registered agent via internal UDS service"""

    @property
    def name(self) -> str:
        return "approval"

    @property
    def help_text(self) -> str:
        return "Approve registered agent (requires agent_approval_enabled=true)"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--agent-name", "-n", required=True, help="Agent name")
        parser.add_argument("--org", "-o", required=True, help="Organization name")
        parser.add_argument("--format", "-f", choices=["text", "json"], default="text")

    def execute(self, args: Namespace) -> int:
        output = Output(args.format)
        client = get_uds_client()

        result = client.approval_agent(args.agent_name, args.org)

        if args.format == "json":
            output.print(result)
            return 0 if result.get("success") else 1

        if result.get("success"):
            output.success(f"Agent '{args.agent_name}' approved successfully")
            if result.get("data"):
                data = result["data"]
                print(f"  Status: {data.get('status', 'published')}")
            return 0
        else:
            output.error(result.get("error", "Approval failed"))
            if result.get("message"):
                print(f"  Message: {result['message']}")
            return 1


class UDSGetCommand(BaseCommand):
    """Get single agent metadata via UDS"""

    @property
    def name(self) -> str:
        return "uds-get"

    @property
    def help_text(self) -> str:
        return "Get agent details (agentcard, status, tag)"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--agent-name", "-n", required=True, help="Agent name")
        parser.add_argument("--org", "-o", required=True, help="Organization name")
        parser.add_argument("--format", "-f", choices=["text", "json"], default="text")

    def execute(self, args: Namespace) -> int:
        output = Output(args.format)
        client = get_uds_client()

        result = client.get_agent(args.agent_name, args.org)

        if args.format == "json":
            output.print(result)
            return 0 if result.get("success") else 1

        if result.get("success"):
            data = result.get("data", {})
            agentcard = data.get("agentcard", {})
            
            print(f"  Agent: {agentcard.get('name')} ({agentcard.get('provider', {}).get('organization')})")
            print(f"  Status: {data.get('status', 'published')}")
            print(f"  Tags: {data.get('tag', [])}")
            
            if agentcard:
                print("\n  AgentCard:")
                import json
                print(json.dumps(agentcard, indent=4, ensure_ascii=False))
            return 0
        else:
            output.error(result.get("error", "Query failed"))
            if result.get("message"):
                print(f"  Message: {result['message']}")
            return 1


class UDSListCommand(BaseCommand):
    """List all agents metadata via UDS"""

    @property
    def name(self) -> str:
        return "uds-list"

    @property
    def help_text(self) -> str:
        return "List all agents (agent_name, organization, status, tag, created_at, updated_at)"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--format", "-f", choices=["text", "json"], default="text")

    def execute(self, args: Namespace) -> int:
        output = Output(args.format)
        client = get_uds_client()

        result = client.list_agents()

        if args.format == "json":
            output.print(result)
            return 0 if result.get("success") else 1

        if result.get("success"):
            agents = result.get("data", {}).get("agents", [])
            if not agents:
                output.info("No agents found")
                return 0
            output.info(f"Found {len(agents)} agents:")
            for agent in agents:
                name = agent.get("agent_name", "unknown")
                org = agent.get("organization", "unknown")
                status = agent.get("status", "unknown")
                tags = agent.get("tag", [])
                created = agent.get("created_at", "")
                updated = agent.get("updated_at", "")
                print(f"  {name} ({org})")
                print(f"    Status: {status}, Tags: {tags}")
                print(f"    Created: {created}, Updated: {updated}")
            return 0
        else:
            output.error(result.get("error", "Query failed"))
            return 1


class AddTagsCommand(BaseCommand):
    """Add tags to agent via UDS"""

    @property
    def name(self) -> str:
        return "add-tags"

    @property
    def help_text(self) -> str:
        return "Add tags to agent (tags will be appended and deduplicated)"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--agent-name", "-n", required=True, help="Agent name")
        parser.add_argument("--org", "-o", required=True, help="Organization name")
        parser.add_argument("--tags", "-t", required=True, help="Tags (comma-separated)")
        parser.add_argument("--format", "-f", choices=["text", "json"], default="text")

    def execute(self, args: Namespace) -> int:
        output = Output(args.format)
        client = get_uds_client()

        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        if not tags:
            output.error("No valid tags provided")
            return 1

        result = client.add_tags(args.agent_name, args.org, tags)

        if args.format == "json":
            output.print(result)
            return 0 if result.get("success") else 1

        if result.get("success"):
            data = result.get("data", {})
            output.success(f"Tags added to '{args.agent_name}'")
            print(f"  Current tags: {data.get('tag', [])}")
            return 0
        else:
            output.error(result.get("error", "Add tags failed"))
            if result.get("message"):
                print(f"  Message: {result['message']}")
            return 1