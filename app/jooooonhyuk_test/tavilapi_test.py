import os
"""
uv run --env-file .env python app/jooooonhyuk_test/tavilapi_test.py
"""

from tavily import TavilyClient


def search_korea_capital():
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    return client.search(query="대한민국의 수도는?")


if __name__ == "__main__":
    result = search_korea_capital()
    print(result)
