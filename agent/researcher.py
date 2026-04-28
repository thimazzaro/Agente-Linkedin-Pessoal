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


def research_topic(topic: Topic, max_results: int = 5) -> List[SearchResult]:
    """
    Searches for recent news/articles on the topic.
    Returns up to max_results articles with clean text content.
    """
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

    # Build a focused query from topic name + keywords
    keyword_sample = ", ".join(topic.keywords[:4])
    query = f"latest news {topic.name}: {keyword_sample}"

    search_kwargs: dict = {
        "query": query,
        "search_depth": "advanced",    # Extracts full page content, not just snippets
        "max_results": max_results,
        "include_raw_content": False,  # Parsed content is cleaner for the LLM
        "topic": "news",               # Bias toward recent news articles
    }

    if topic.sources:
        search_kwargs["include_domains"] = topic.sources

    response = client.search(**search_kwargs)

    results = []
    for r in response.get("results", []):
        if not r.get("content"):
            continue
        results.append(SearchResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            content=r.get("content", ""),
            published_date=r.get("published_date"),
        ))

    return results
