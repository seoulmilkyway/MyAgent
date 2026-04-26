import os
from langchain_core.tools import tool

def get_duckduckgo_tool():
    from langchain_community.tools import DuckDuckGoSearchRun
    @tool
    def search_web(query: str) -> str:
        """Search the web for the given query using DuckDuckGo and return the results."""
        search = DuckDuckGoSearchRun()
        return search.run(query)
    return search_web

def get_search_tool():
    """Factory function to return the selected search tool based on SEARCH_PROVIDER env var."""
    provider = os.getenv("SEARCH_PROVIDER", "duckduckgo").lower()
    
    if provider == "tavily":
        try:
            from langchain_community.tools.tavily_search import TavilySearchResults
            # Tavily Search requires TAVILY_API_KEY environment variable
            # Returns a tool that searches the web and yields comprehensive results
            return TavilySearchResults(max_results=3)
        except ImportError:
            print("[Warning] 'tavily-python' package not found. Falling back to DuckDuckGo.")
            return get_duckduckgo_tool()
            
    elif provider == "google":
        try:
            from langchain_community.utilities import SerpAPIWrapper
            from langchain_core.tools import Tool
            # Requires SERPAPI_API_KEY environment variable
            search = SerpAPIWrapper()
            return Tool(
                name="search_web",
                description="Search the web for current events or facts using Google.",
                func=search.run,
            )
        except ImportError:
            print("[Warning] 'google-search-results' package not found. Falling back to DuckDuckGo.")
            return get_duckduckgo_tool()
            
    else:
        # Default to DuckDuckGo
        return get_duckduckgo_tool()
