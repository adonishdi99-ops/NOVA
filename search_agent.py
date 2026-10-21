# search_agent.py
import os
import time
import warnings

warnings.filterwarnings("ignore", category=ResourceWarning)

# ── Tavily (primary) ──────────────────────────────────────────────────────────
TAVILY_AVAILABLE = False
try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    pass

# ── DDG (fallback) ────────────────────────────────────────────────────────────
DDGS_AVAILABLE = False
try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        DDGS_AVAILABLE = True
    except ImportError:
        pass

MAX_SNIPPET_CHARS = 400
MAX_RESULTS       = 5
RETRY_DELAY       = 2.0


def _search_tavily(query: str) -> str | None:
    """Primary search via Tavily API — designed for AI agents, no rate-limiting."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key or api_key.strip() == "":
        print("[search] Tavily API key not set, skipping Tavily")
        return None

    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            max_results=MAX_RESULTS,
            search_depth="basic",          # "basic" is faster, "advanced" for deeper research
            include_answer=False,           # we want raw results to summarize ourselves
            include_raw_content=False,
        )

        results = response.get("results", [])
        if not results:
            print(f"[search] Tavily: no results for: '{query}'")
            return None

        parts = []
        for r in results:
            title = r.get("title", "").strip()
            body  = r.get("content", "").strip()[:MAX_SNIPPET_CHARS]
            if title or body:
                parts.append(f"{title}: {body}")

        formatted = "\n\n".join(parts)
        print(f"[search] Tavily: {len(parts)} results for: '{query}'")
        return formatted or None

    except Exception as e:
        print(f"[search] Tavily error: {e}")
        return None


def _search_ddg(query: str) -> str | None:
    """Fallback search via DuckDuckGo. Retries once on empty result."""
    if not DDGS_AVAILABLE:
        print("[search] DDG not available (run: pip install ddgs)")
        return None

    for attempt in range(2):
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=MAX_RESULTS))

            if not results:
                print(f"[search] DDG: no results (attempt {attempt + 1}) for: '{query}'")
                if attempt == 0:
                    time.sleep(RETRY_DELAY)
                    continue
                return None

            parts = []
            for r in results:
                title = r.get("title", "").strip()
                body  = r.get("body",  "").strip()[:MAX_SNIPPET_CHARS]
                if title or body:
                    parts.append(f"{title}: {body}")

            formatted = "\n\n".join(parts)
            print(f"[search] DDG: {len(parts)} results for: '{query}'")
            return formatted or None

        except Exception as e:
            print(f"[search] DDG error (attempt {attempt + 1}): {e}")
            if attempt == 0:
                time.sleep(RETRY_DELAY)

    return None


def web_search(query: str) -> str | None:
    """
    Search the web. Tries Tavily first (best quality, no rate-limiting),
    falls back to DuckDuckGo if Tavily fails or isn't configured.
    Returns formatted snippets or None.
    """
    # ── Try Tavily first ──────────────────────────────────────────────────────
    if TAVILY_AVAILABLE and os.getenv("TAVILY_API_KEY", "").strip():
        result = _search_tavily(query)
        if result:
            return result
        print("[search] Tavily failed, falling back to DDG...")

    # ── Fallback to DDG ───────────────────────────────────────────────────────
    if DDGS_AVAILABLE:
        return _search_ddg(query)

    print("[search] No search provider available. Install: pip install tavily-python ddgs")
    return None