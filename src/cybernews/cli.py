import logging
import os
import shlex
from pathlib import Path
from typing import Dict, List

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cybernews.config import DB_PATH, DEFAULT_LIMIT, DEFAULT_RSS_FEEDS, load_configured_feeds, save_configured_feeds
from cybernews.models import Article, SourceStatus
from cybernews.service import get_in_memory_stats, get_latest_news
from cybernews.state import StateManager

app = typer.Typer(
    help="CyberNews: A command-line cybersecurity news aggregation and intelligence tool."
)

logger = logging.getLogger("cybernews.cli")

CATEGORY_STYLES = {
    "ransomware": "bold red",
    "data_breach": "bold magenta",
    "malware": "red",
    "vulnerability": "bold yellow",
    "exploit": "yellow",
    "apt": "bold cyan",
    "phishing": "bold orange1",
    "security_research": "bold green",
    "general": "dim white",
}

def setup_logging() -> None:
    """Sets up file logging under logs/cybernews.log."""
    log_dir = Path("logs")
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "cybernews.log"
        logging.basicConfig(
            filename=str(log_file),
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            encoding="utf-8",
        )
    except Exception:
        # Failsafe if logging directory is not writable
        logging.basicConfig(level=logging.CRITICAL)

def display_articles_table(articles: List[Article], limit: int | None, console: Console) -> None:
    """Formats and prints a list of articles using a Rich Table."""
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("ID", style="dim", width=12)
    table.add_column("Category", width=18)
    table.add_column("Source", style="cyan", width=18)
    table.add_column("Title", style="white")
    table.add_column("Published At", style="green", width=17)

    display_list = articles[:limit] if limit else articles

    for art in display_list:
        style = CATEGORY_STYLES.get(art.category.lower(), "white")
        formatted_date = art.published_at.strftime("%Y-%m-%d %H:%M")
        table.add_row(
            art.id,
            f"[{style}]{art.category}[/{style}]",
            art.source,
            art.title,
            formatted_date,
        )

    console.print(table)
    if limit and len(articles) > limit:
        console.print(
            f"[dim]Showing {limit} of {len(articles)} articles. Use '--limit' or interactive mode to view all.[/dim]"
        )

def display_stats_report(stats: dict, title: str, console: Console) -> None:
    """Displays article and source metrics."""
    if stats["total"] == 0:
        console.print(f"[bold yellow]=== {title} ===[/bold yellow]")
        console.print("No articles are currently available.")
        return

    console.print(f"[bold blue]=== {title} ===[/bold blue]")
    console.print(f"Total Articles: {stats['total']}")

    if "success_sources" in stats:
        console.print(f"Successful Sources: {stats['success_sources']}")
        console.print(f"Failed Sources: {stats['failed_sources']}")

    if stats.get("last_fetch_time"):
        formatted_fetch = stats["last_fetch_time"].strftime("%Y-%m-%d %H:%M:%S UTC")
        console.print(f"Last Fetched: {formatted_fetch}")

    if stats["oldest_pub"]:
        console.print(f"Oldest Publication: {stats['oldest_pub'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
    if stats["latest_pub"]:
        console.print(f"Latest Publication: {stats['latest_pub'].strftime('%Y-%m-%d %H:%M:%S UTC')}")

    console.print("\n[bold]Articles by Category:[/bold]")
    cat_table = Table(box=None, padding=(0, 2))
    cat_table.add_column("Category", style="cyan")
    cat_table.add_column("Count", style="white")

    sorted_cats = sorted(stats["categories"].items(), key=lambda x: x[1], reverse=True)
    for cat, count in sorted_cats:
        style = CATEGORY_STYLES.get(cat.lower(), "white")
        cat_table.add_row(f"[{style}]{cat}[/{style}]", str(count))
    console.print(cat_table)

    console.print("\n[bold]Articles by Source:[/bold]")
    src_table = Table(box=None, padding=(0, 2))
    src_table.add_column("Source", style="cyan")
    src_table.add_column("Count", style="white")

    sorted_srcs = sorted(stats["sources"].items(), key=lambda x: x[1], reverse=True)
    for src, count in sorted_srcs:
        src_table.add_row(src, str(count))
    console.print(src_table)

def handle_fetch(state_manager: StateManager, save: bool, console: Console) -> None:
    """Core logic for the fetch command."""
    with console.status("[bold cyan]Fetching RSS feeds...", spinner="dots"):
        articles = get_latest_news(state_manager, force_refresh=True)

    success_count = sum(1 for s in state_manager.source_statuses.values() if s.success)
    failed_count = sum(1 for s in state_manager.source_statuses.values() if not s.success)
    total_raw = sum(s.articles_count for s in state_manager.source_statuses.values())

    console.print(f"✓ Fetched {len(state_manager.source_statuses)} sources")
    console.print(f"✓ Successful: {success_count}, Failed: {failed_count}")
    console.print(f"✓ Retrieved {total_raw} articles")
    console.print(f"✓ {len(articles)} unique articles after deduplication")

    if save:
        from cybernews.storage.jsonl import save_articles
        with console.status("[bold cyan]Saving to persistent archive...", spinner="dots"):
            saved, skipped = save_articles(articles, DB_PATH)
        console.print(f"✓ Saved {saved} new articles to [green]{DB_PATH}[/green]")
        console.print(f"✓ Skipped {skipped} duplicates")

def handle_latest(state_manager: StateManager, limit: int, console: Console) -> None:
    """Core logic for latest command."""
    if not state_manager.current_articles:
        with console.status("[bold cyan]Loading latest articles...", spinner="dots"):
            get_latest_news(state_manager)

    articles = state_manager.current_articles
    if not articles:
        console.print("[bold yellow]No articles loaded.[/bold yellow]")
        return

    display_articles_table(articles, limit, console)

def handle_search(state_manager: StateManager, query: str, console: Console) -> None:
    """Core logic for search command."""
    if not state_manager.current_articles:
        with console.status("[bold cyan]Loading articles...", spinner="dots"):
            get_latest_news(state_manager)

    articles = state_manager.current_articles
    query_lower = query.lower()
    matching = []

    for art in articles:
        if (
            query_lower in art.title.lower()
            or query_lower in art.summary.lower()
            or query_lower in art.source.lower()
            or query_lower in art.category.lower()
        ):
            matching.append(art)

    if not matching:
        console.print(f"[bold yellow]No in-memory articles match: '{query}'[/bold yellow]")
        return

    console.print(f"[bold green]Found {len(matching)} matching articles in memory:[/bold green]")
    display_articles_table(matching, None, console)

def handle_category(state_manager: StateManager, category: str, console: Console) -> None:
    """Core logic for category filtering."""
    if not state_manager.current_articles:
        with console.status("[bold cyan]Loading articles...", spinner="dots"):
            get_latest_news(state_manager)

    articles = state_manager.current_articles
    matching = [art for art in articles if art.category.lower() == category.lower()]

    if not matching:
        console.print(f"[bold yellow]No in-memory articles found in category: '{category}'[/bold yellow]")
        return

    console.print(f"[bold green]Found {len(matching)} articles in category '{category}':[/bold green]")
    display_articles_table(matching, None, console)

def handle_source(state_manager: StateManager, source: str, console: Console) -> None:
    """Core logic for source filtering."""
    if not state_manager.current_articles:
        with console.status("[bold cyan]Loading articles...", spinner="dots"):
            get_latest_news(state_manager)

    articles = state_manager.current_articles
    matching = [art for art in articles if source.lower() in art.source.lower()]

    if not matching:
        console.print(f"[bold yellow]No in-memory articles found from source: '{source}'[/bold yellow]")
        return

    console.print(f"[bold green]Found {len(matching)} articles from source '{source}':[/bold green]")
    display_articles_table(matching, None, console)

def handle_read(state_manager: StateManager, art_id: str, console: Console) -> None:
    """Core logic for reading a detailed article."""
    if not state_manager.current_articles:
        with console.status("[bold cyan]Loading articles...", spinner="dots"):
            get_latest_news(state_manager)

    # First look up in-memory
    target = None
    for art in state_manager.current_articles:
        if art.id == art_id:
            target = art
            break

    # Next look up in persistence file
    if not target:
        from cybernews.storage.jsonl import load_articles
        saved_articles = load_articles(DB_PATH)
        for art in saved_articles:
            if art.id == art_id:
                target = art
                break

    if not target:
        console.print(f"[bold red]Error: Article with ID '{art_id}' not found.[/bold red]")
        return

    style = CATEGORY_STYLES.get(target.category.lower(), "white")
    content = (
        f"[bold]Source:[/bold] {target.source}\n"
        f"[bold]Category:[/bold] [{style}]{target.category}[/{style}]\n"
        f"[bold]Published At:[/bold] {target.published_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        f"[bold]URL:[/bold] [underline cyan]{target.url}[/underline cyan]\n\n"
        f"[bold]Summary:[/bold]\n{target.summary}"
    )

    console.print(Panel(content, title=f"[bold white]{target.title}[/bold white]", border_style="blue"))

def handle_stats(state_manager: StateManager, console: Console) -> None:
    """Core logic for display in-memory stats."""
    if not state_manager.current_articles:
        with console.status("[bold cyan]Loading articles...", spinner="dots"):
            get_latest_news(state_manager)

    stats = get_in_memory_stats(state_manager)
    display_stats_report(stats, "CyberNews Statistics (In-Memory)", console)

def handle_save(state_manager: StateManager, console: Console) -> None:
    """Core logic for saving current state to file."""
    if not state_manager.current_articles:
        console.print("[bold yellow]No current in-memory articles to save. Fetching latest first...[/bold yellow]")
        with console.status("[bold cyan]Fetching RSS feeds...", spinner="dots"):
            get_latest_news(state_manager)

    articles = state_manager.current_articles
    if not articles:
        console.print("[bold yellow]No articles retrieved. Saving cancelled.[/bold yellow]")
        return

    from cybernews.storage.jsonl import save_articles
    with console.status("[bold cyan]Saving to JSONL archive...", spinner="dots"):
        saved, skipped = save_articles(articles, DB_PATH)

    console.print(f"✓ Articles considered: {len(articles)}")
    console.print(f"✓ Saved {saved} new articles to [green]{DB_PATH}[/green]")
    console.print(f"✓ Skipped {skipped} duplicates")

def handle_saved(console: Console) -> None:
    """Core logic for displaying saved articles."""
    from cybernews.storage.jsonl import load_articles
    if not DB_PATH.exists():
        console.print(f"[bold yellow]Archive '{DB_PATH}' does not exist yet. Run 'save' or 'fetch --save' first.[/bold yellow]")
        return

    with console.status("[bold cyan]Loading archived articles...", spinner="dots"):
        articles = load_articles(DB_PATH)

    if not articles:
        console.print("[bold yellow]Persistent archive is empty.[/bold yellow]")
        return

    articles = sorted(articles, key=lambda x: x.published_at, reverse=True)
    console.print(f"[bold green]Displaying {len(articles)} saved articles:[/bold green]")
    display_articles_table(articles, None, console)

def handle_saved_search(query: str, console: Console) -> None:
    """Core logic for searching the archive."""
    from cybernews.storage.jsonl import search_articles
    if not DB_PATH.exists():
        console.print(f"[bold yellow]Archive '{DB_PATH}' does not exist yet.[/bold yellow]")
        return

    with console.status("[bold cyan]Searching archive...", spinner="dots"):
        results = search_articles(query, DB_PATH)

    if not results:
        console.print(f"[bold yellow]No archived articles match query: '{query}'[/bold yellow]")
        return

    results = sorted(results, key=lambda x: x.published_at, reverse=True)
    console.print(f"[bold green]Found {len(results)} matching archived articles:[/bold green]")
    display_articles_table(results, None, console)

def handle_saved_category(category: str, console: Console) -> None:
    """Core logic for category filtering the archive."""
    from cybernews.storage.jsonl import filter_articles_by_category
    if not DB_PATH.exists():
        console.print(f"[bold yellow]Archive '{DB_PATH}' does not exist yet.[/bold yellow]")
        return

    with console.status("[bold cyan]Filtering archive category...", spinner="dots"):
        results = filter_articles_by_category(category, DB_PATH)

    if not results:
        console.print(f"[bold yellow]No archived articles found in category: '{category}'[/bold yellow]")
        return

    results = sorted(results, key=lambda x: x.published_at, reverse=True)
    console.print(f"[bold green]Found {len(results)} archived articles in category '{category}':[/bold green]")
    display_articles_table(results, None, console)

def handle_saved_stats(console: Console) -> None:
    """Core logic for displaying archive stats."""
    from cybernews.storage.jsonl import get_archive_stats
    if not DB_PATH.exists():
        console.print(f"[bold yellow]Archive '{DB_PATH}' does not exist yet.[/bold yellow]")
        return

    with console.status("[bold cyan]Computing archive stats...", spinner="dots"):
        stats = get_archive_stats(DB_PATH)

    display_stats_report(stats, "CyberNews Persistent Archive Statistics", console)

def handle_sources(state_manager: StateManager, console: Console) -> None:
    """Core logic for listing RSS sources and statuses."""
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Source Name", style="cyan", width=22)
    table.add_column("Status", width=12)
    table.add_column("Count", style="green", width=8)
    table.add_column("URL", style="dim", width=48)
    table.add_column("Error Message", style="red")

    feeds = load_configured_feeds()
    if not state_manager.source_statuses:
        for name, url in feeds.items():
            table.add_row(name, "[yellow]Pending[/yellow]", "-", url, "-")
    else:
        for name, url in feeds.items():
            status = state_manager.source_statuses.get(name)
            if status:
                status_text = "[bold green]Success[/bold green]" if status.success else "[bold red]Failed[/bold red]"
                cnt = str(status.articles_count) if status.success else "0"
                err = status.error_message or "-"
                table.add_row(name, status_text, cnt, url, err)
            else:
                table.add_row(name, "[yellow]Pending[/yellow]", "-", url, "-")

    console.print(table)

def handle_source_add(url: str, console: Console) -> None:
    """Core logic to fetch feed to get name, then add it to feeds.json."""
    import feedparser
    import urllib.request
    from urllib.parse import urlparse

    with console.status("[bold cyan]Fetching feed to verify and identify name...", spinner="dots"):
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CyberNews/0.1.0"}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10.0) as response:
                raw_data = response.read()
                parsed = feedparser.parse(raw_data)
                if not parsed.entries and parsed.bozo:
                    raise ValueError(f"Malformed or empty feed: {parsed.bozo_exception}")
                
                feed_title = parsed.feed.get("title", "").strip()
                if not feed_title:
                    parsed_url = urlparse(url)
                    feed_title = parsed_url.netloc or "Custom Source"
        except Exception as e:
            console.print(f"[bold red]Error: Failed to fetch and parse RSS feed at '{url}': {e}[/bold red]")
            return

    feeds = load_configured_feeds()
    
    # Check if URL already exists
    for name, feed_url in feeds.items():
        if feed_url.strip().lower() == url.strip().lower():
            console.print(f"[bold yellow]Source with URL '{url}' already exists as '{name}'.[/bold yellow]")
            return

    # De-conflict name if title already exists
    unique_title = feed_title
    counter = 1
    while unique_title in feeds:
        unique_title = f"{feed_title} ({counter})"
        counter += 1
        
    feeds[unique_title] = url
    save_configured_feeds(feeds)
    console.print(f"✓ Successfully added source [bold green]'{unique_title}'[/bold green]: [dim]{url}[/dim]")

def handle_source_del(url_or_name: str, console: Console) -> None:
    """Deletes a source matching the specified link or name."""
    feeds = load_configured_feeds()
    
    found_key = None
    url_stripped = url_or_name.strip().lower()
    for name, feed_url in feeds.items():
        if feed_url.strip().lower() == url_stripped or name.strip().lower() == url_stripped:
            found_key = name
            break
            
    if not found_key:
        console.print(f"[bold red]Error: No source found matching URL or Name: '{url_or_name}'[/bold red]")
        return
        
    deleted_url = feeds.pop(found_key)
    save_configured_feeds(feeds)
    console.print(f"✓ Successfully deleted source [bold red]'{found_key}'[/bold red]: [dim]{deleted_url}[/dim]")

def display_shell_help(console: Console) -> None:
    """Prints shell help instructions."""
    table = Table(box=None)
    table.add_column("Command", style="bold green", width=26)
    table.add_column("Description", style="white")

    table.add_row("fetch", "Force fetch latest RSS feeds into memory")
    table.add_row("fetch --save", "Force fetch and explicitly save to JSONL archive")
    table.add_row("latest", "Display latest articles (fetches if cache empty)")
    table.add_row("search <query>", "Search in-memory articles case-insensitively")
    table.add_row("category <category>", "Filter in-memory articles by category")
    table.add_row("source <source>", "Filter in-memory articles by source")
    table.add_row("source add <link>", "Add a new RSS source dynamically")
    table.add_row("source del <link/name>", "Delete an RSS source dynamically")
    table.add_row("read <id>", "Read detailed article view")
    table.add_row("stats", "Display in-memory articles & source statistics")
    table.add_row("save", "Save current in-memory articles to JSONL archive")
    table.add_row("saved", "Display saved articles from JSONL archive")
    table.add_row("saved-search <query>", "Search only the persisted JSONL archive")
    table.add_row("saved-category <cat>", "Filter only the persisted JSONL archive")
    table.add_row("saved-stats", "Display persistent JSONL archive statistics")
    table.add_row("sources", "Display configured RSS feeds & retrieval statuses")
    table.add_row("help", "Show this help menu")
    table.add_row("exit", "Exit the interactive shell")

    console.print("\n[bold]Available Commands in Shell:[/bold]")
    console.print(table)

def shell_mode(state_manager: StateManager) -> None:
    """Launches the interactive CLI loop."""
    console = Console()

    sources_count = len(load_configured_feeds())
    current_count = len(state_manager.current_articles)

    startup_text = (
        f"[bold cyan]CyberNews Interactive Shell[/bold cyan]\n\n"
        f"• [bold]Configured RSS Sources:[/bold] {sources_count}\n"
        f"• [bold]Cache Duration:[/bold] {state_manager.cache_duration_secs // 60} minutes\n"
        f"• [bold]Current In-Memory Articles:[/bold] {current_count}\n"
        f"• [bold]Persistent Archive Path:[/bold] {DB_PATH}\n\n"
        f"Type [bold green]help[/bold green] to list commands or [bold red]exit[/bold red] to quit."
    )
    console.print(Panel(startup_text, border_style="cyan", title="Welcome", title_align="left"))

    while True:
        try:
            user_input = console.input("[bold yellow]cybernews>[/bold yellow] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold red]Exiting CyberNews Interactive Shell. Goodbye![/bold red]")
            break

        if not user_input:
            continue

        try:
            tokens = shlex.split(user_input)
        except Exception as e:
            console.print(f"[bold red]Error parsing command:[/bold red] {e}")
            continue

        cmd = tokens[0].lower()
        args = tokens[1:]

        if cmd == "exit":
            console.print("[bold red]Exiting CyberNews Interactive Shell. Goodbye![/bold red]")
            break
        elif cmd == "help":
            display_shell_help(console)
        elif cmd == "fetch":
            save_flag = "--save" in args
            handle_fetch(state_manager, save_flag, console)
        elif cmd == "latest":
            limit = DEFAULT_LIMIT
            if "--limit" in args:
                idx = args.index("--limit")
                if idx + 1 < len(args):
                    try:
                        limit = int(args[idx + 1])
                    except ValueError:
                        console.print("[bold red]Invalid limit value.[/bold red]")
                        continue
            handle_latest(state_manager, limit, console)
        elif cmd == "search":
            if not args:
                console.print("[bold red]Error: Search query cannot be empty.[/bold red]")
                continue
            query = " ".join(args)
            handle_search(state_manager, query, console)
        elif cmd == "category":
            if not args:
                console.print("[bold red]Error: Category cannot be empty.[/bold red]")
                continue
            category = args[0]
            handle_category(state_manager, category, console)
        elif cmd == "source":
            if not args:
                console.print("[bold red]Error: Source cannot be empty.[/bold red]")
                continue
            action = args[0].lower()
            if action == "add":
                if len(args) < 2:
                    console.print("[bold red]Error: Please specify the RSS link to add.[/bold red]")
                    continue
                handle_source_add(args[1], console)
            elif action == "del":
                if len(args) < 2:
                    console.print("[bold red]Error: Please specify the RSS link or name to delete.[/bold red]")
                    continue
                handle_source_del(args[1], console)
            else:
                source = " ".join(args)
                handle_source(state_manager, source, console)
        elif cmd == "read":
            if not args:
                console.print("[bold red]Error: Article ID cannot be empty.[/bold red]")
                continue
            art_id = args[0]
            handle_read(state_manager, art_id, console)
        elif cmd == "stats":
            handle_stats(state_manager, console)
        elif cmd == "save":
            handle_save(state_manager, console)
        elif cmd == "saved":
            handle_saved(console)
        elif cmd == "saved-search":
            if not args:
                console.print("[bold red]Error: Search query cannot be empty.[/bold red]")
                continue
            query = " ".join(args)
            handle_saved_search(query, console)
        elif cmd == "saved-category":
            if not args:
                console.print("[bold red]Error: Category cannot be empty.[/bold red]")
                continue
            category = args[0]
            handle_saved_category(category, console)
        elif cmd == "saved-stats":
            handle_saved_stats(console)
        elif cmd == "sources":
            handle_sources(state_manager, console)
        else:
            console.print(f"[bold red]Unknown command:[/bold red] '{cmd}'. Type 'help' for usage.")

# --- Direct Typer CLI Commands ---

@app.command(name="fetch")
def cli_fetch(
    save: bool = typer.Option(False, "--save", help="Directly save fetched articles to the archive")
) -> None:
    """Fetch the latest news from RSS feeds into memory (forces a cache refresh)."""
    setup_logging()
    state_manager = StateManager()
    console = Console()
    handle_fetch(state_manager, save, console)

@app.command(name="latest")
def cli_latest(
    limit: int = typer.Option(DEFAULT_LIMIT, "--limit", "-l", help="Limit results to N articles")
) -> None:
    """Display the latest in-memory articles (auto-fetches if empty)."""
    setup_logging()
    state_manager = StateManager()
    console = Console()
    handle_latest(state_manager, limit, console)

@app.command(name="search")
def cli_search(query: str = typer.Argument(..., help="Search query")) -> None:
    """Search for keywords in in-memory articles."""
    setup_logging()
    state_manager = StateManager()
    console = Console()
    handle_search(state_manager, query, console)

@app.command(name="category")
def cli_category(category: str = typer.Argument(..., help="Category to filter by")) -> None:
    """Filter in-memory articles by category."""
    setup_logging()
    state_manager = StateManager()
    console = Console()
    handle_category(state_manager, category, console)

@app.command(name="source")
def cli_source(
    args: List[str] = typer.Argument(
        ...,
        help="Source name to filter OR 'add <link>' to add a source OR 'del <link/name>' to delete a source"
    )
) -> None:
    """Manage and filter RSS sources.
    
    Filter articles:
      cybernews source "The Hacker News"
    
    Add a source:
      cybernews source add "https://example.com/feed"
      
    Delete a source:
      cybernews source del "https://example.com/feed"
    """
    setup_logging()
    console = Console()
    
    if not args:
        console.print("[bold red]Error: Source query or action is required.[/bold red]")
        return
        
    action = args[0].lower()
    
    if action == "add":
        if len(args) < 2:
            console.print("[bold red]Error: Please specify the RSS link to add.[/bold red]")
            return
        handle_source_add(args[1], console)
    elif action == "del":
        if len(args) < 2:
            console.print("[bold red]Error: Please specify the RSS link or name to delete.[/bold red]")
            return
        handle_source_del(args[1], console)
    else:
        query = " ".join(args)
        state_manager = StateManager()
        handle_source(state_manager, query, console)

@app.command(name="read")
def cli_read(article_id: str = typer.Argument(..., help="Short article ID")) -> None:
    """Show detailed view of an article by its ID."""
    setup_logging()
    state_manager = StateManager()
    console = Console()
    handle_read(state_manager, article_id, console)

@app.command(name="stats")
def cli_stats() -> None:
    """Show statistics about current in-memory articles."""
    setup_logging()
    state_manager = StateManager()
    console = Console()
    handle_stats(state_manager, console)

@app.command(name="save")
def cli_save() -> None:
    """Save in-memory articles explicitly to the persistent JSONL archive."""
    setup_logging()
    state_manager = StateManager()
    console = Console()
    handle_save(state_manager, console)

@app.command(name="saved")
def cli_saved() -> None:
    """Show all articles saved in the persistent JSONL archive."""
    setup_logging()
    console = Console()
    handle_saved(console)

@app.command(name="saved-search")
def cli_saved_search(query: str = typer.Argument(..., help="Search query")) -> None:
    """Search for keywords in the persistent JSONL archive."""
    setup_logging()
    console = Console()
    handle_saved_search(query, console)

@app.command(name="saved-category")
def cli_saved_category(category: str = typer.Argument(..., help="Category to filter by")) -> None:
    """Filter archived articles by category."""
    setup_logging()
    console = Console()
    handle_saved_category(category, console)

@app.command(name="saved-stats")
def cli_saved_stats() -> None:
    """Show statistics for the persistent JSONL archive."""
    setup_logging()
    console = Console()
    handle_saved_stats(console)

@app.command(name="sources")
def cli_sources() -> None:
    """List configured RSS sources and their latest retrieval status."""
    setup_logging()
    state_manager = StateManager()
    console = Console()
    handle_sources(state_manager, console)

@app.command(name="shell")
def cli_shell() -> None:
    """Launch the interactive shell maintaining in-memory state."""
    setup_logging()
    state_manager = StateManager()
    shell_mode(state_manager)

if __name__ == "__main__":
    app()
