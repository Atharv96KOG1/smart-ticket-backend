import argparse
import json
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent / "src"))

load_dotenv()

console = Console()

SAMPLE_TICKETS_PATH = Path(__file__).parent / "data" / "sample_tickets.json"
MAX_TICKET_CHARS = 2000

PRIORITY_COLOR = {"High": "bold red", "Medium": "yellow", "Low": "green"}


def route_direct(text: str) -> dict:
    """Import the router in-process — no server required."""
    from smart_ticket_router.core.router import route_ticket

    result = route_ticket(text)
    return result.model_dump(mode="json", exclude_none=True)


def route_via_api(text: str, base_url: str) -> dict:
    resp = httpx.post(f"{base_url}/route", json={"message": text}, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"API error {resp.status_code}: {resp.json().get('detail', resp.text)}")
    return resp.json()


def render_result(ticket_text: str, result: dict, elapsed: float) -> None:
    priority = result.get("priority", "?")
    color = PRIORITY_COLOR.get(priority, "white")

    body = (
        f"[bold]Category:[/bold]      {result.get('category')}\n"
        f"[bold]Priority:[/bold]      [{color}]{priority}[/{color}]\n"
        f"[bold]Assigned team:[/bold] {result.get('assigned_team')}\n"
        f"[bold]Reasoning:[/bold]     {result.get('reasoning')}"
    )
    for issue in result.get("other_issues") or []:
        issue_color = PRIORITY_COLOR.get(issue.get("priority"), "white")
        body += (
            f"\n[bold]Other issue:[/bold]    {issue.get('category')} "
            f"[{issue_color}]({issue.get('priority')})[/{issue_color}]"
        )
    if result.get("confidence"):
        body += f"\n[bold]Confidence:[/bold]     {result['confidence']}"

    console.print(Panel(body, title=f'"{ticket_text[:60]}"', subtitle=f"{elapsed*1000:.0f} ms"))
    console.print(Panel(json.dumps(result, indent=2), title="raw JSON", border_style="dim"))


def cmd_route(args: argparse.Namespace) -> None:
    text = console.input("[bold cyan]Enter ticket message:[/bold cyan] ").strip()
    if not text:
        console.print("[red]Blank input — nothing sent.[/red]")
        return
    if len(text) > MAX_TICKET_CHARS:
        console.print(
            f"[yellow]Message is {len(text)} chars, over the {MAX_TICKET_CHARS} cap — "
            f"it will be trimmed server-side, not blindly truncated.[/yellow]"
        )

    start = time.perf_counter()
    try:
        if args.api:
            result = route_via_api(text, args.url)
        else:
            result = route_direct(text)
    except Exception as e:
        console.print(f"[bold red]Routing failed:[/bold red] {e}")
        return
    elapsed = time.perf_counter() - start

    render_result(text, result, elapsed)


def cmd_demo(args: argparse.Namespace) -> None:
    tickets = json.loads(SAMPLE_TICKETS_PATH.read_text())

    table = Table(title="Smart Ticket Router — 20-Ticket Demo")
    table.add_column("#", justify="right")
    table.add_column("Ticket", max_width=40)
    table.add_column("Category")
    table.add_column("Priority")
    table.add_column("Team")
    table.add_column("ms", justify="right")

    total_elapsed = 0.0
    routed_count = 0

    for i, ticket in enumerate(tickets, start=1):
        text = ticket["text"]

        if not text.strip():
            table.add_row(str(i), "(blank)", "—", "—", "Never reaches API", "0")
            continue

        start = time.perf_counter()
        try:
            result = route_via_api(text, args.url) if args.api else route_direct(text)
        except Exception as e:
            table.add_row(str(i), text[:40], "[red]ERROR[/red]", str(e)[:30], "", "")
            continue
        elapsed_ms = (time.perf_counter() - start) * 1000
        total_elapsed += elapsed_ms
        routed_count += 1

        priority = result.get("priority", "?")
        color = PRIORITY_COLOR.get(priority, "white")
        table.add_row(
            str(i),
            text[:40],
            result.get("category", "?"),
            f"[{color}]{priority}[/{color}]",
            result.get("assigned_team", "?"),
            f"{elapsed_ms:.0f}",
        )

    console.print(table)

    manual_seconds_low, manual_seconds_high = 30 * routed_count, 90 * routed_count
    console.print(
        Panel(
            f"AI routed {routed_count} tickets in {total_elapsed/1000:.2f}s "
            f"(avg {total_elapsed/max(routed_count,1):.0f} ms/ticket).\n"
            f"Manual triage of the same {routed_count} tickets would take an estimated "
            f"{manual_seconds_low}-{manual_seconds_high}s (~30-90s/ticket).",
            title="Before / After",
            border_style="green",
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Smart Ticket Router CLI")
    parser.add_argument("--api", action="store_true", help="call a running FastAPI server instead of routing in-process")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="FastAPI base URL (with --api)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("route", help="interactively route a single ticket")
    sub.add_parser("demo", help="batch-route the 20 sample tickets")

    args = parser.parse_args()

    if args.command == "route":
        cmd_route(args)
    elif args.command == "demo":
        cmd_demo(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
