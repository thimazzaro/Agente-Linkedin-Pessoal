"""
Searches the web for recent content on a given topic.
Uses Tavily — optimized for LLM agents, returns structured text (not just links).
Free tier: 1,000 searches/month — enough for 20 posts/month with room to spare.
"""
import os
from dataclasses import dataclass
from typing import List, Optional
from tavily import TavilyClient
from config.schema import Topic


@dataclass
class SearchResult:
    title: str
    url: str
    content: str        # Clean extracted text, ready for the LLM
    published_date: Optional[str] = None


def research_topic(
    topic: Topic,
    max_results: int = 5,
    exclude_urls: Optional[List[str]] = None,
) -> List[SearchResult]:
    """
    Searches for recent news/articles on the topic.
    exclude_urls: URLs already used in previous (blocked) attempts — Tavily will skip them.
    """
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

    # Rotate keyword sample on retries to vary results
    keyword_sample = ", ".join(topic.keywords[:4])
    query = f"latest news {topic.name}: {keyword_sample}"

    search_kwargs: dict = {
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
        "include_raw_content": False,
        "topic": "news",
    }

    if topic.sources:
        search_kwargs["include_domains"] = topic.sources

    if exclude_urls:
        # Extract domains from excluded URLs to avoid entire sites that produced bad content
        exclude_domains = list({
            url.split("/")[2] for url in exclude_urls if url.startswith("http")
        })
        search_kwargs["exclude_domains"] = exclude_domains

    response = client.search(**search_kwargs)

    results = []
    for r in response.get("results", []):
        if not r.get("content"):
            continue
        if exclude_urls and r.get("url") in exclude_urls:
            continue
        results.append(SearchResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            content=r.get("content", ""),
            published_date=r.get("published_date"),
        ))

    return results
