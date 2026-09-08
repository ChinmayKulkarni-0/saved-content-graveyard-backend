import logging
from urllib.parse import quote

from app.schemas.pipeline import ContentType, Link, LinkType

logger = logging.getLogger(__name__)


class MovieService:
    """Finds streaming links for movies and TV shows. Mock implementation for now."""

    MOCK_MOVIES: dict[str, dict] = {
        "dune": {
            "title": "Dune",
            "links": [
                {"label": "Watch on HBO Max", "url": "https://max.com/movies/dune", "type": LinkType.STREAM},
                {"label": "Rent on Apple TV", "url": "https://tv.apple.com/movie/dune", "type": LinkType.STREAM},
                {"label": "Buy on Amazon", "url": "https://amazon.com/dp/dune-movie", "type": LinkType.BUY},
            ],
        },
        "oppenheimer": {
            "title": "Oppenheimer",
            "links": [
                {"label": "Watch on Peacock", "url": "https://peacocktv.com/movies/oppenheimer", "type": LinkType.STREAM},
                {"label": "Rent on Vudu", "url": "https://vudu.com/content/movies/oppenheimer", "type": LinkType.STREAM},
            ],
        },
        "barbie": {
            "title": "Barbie",
            "links": [
                {"label": "Watch on Max", "url": "https://max.com/movies/barbie", "type": LinkType.STREAM},
                {"label": "Rent on Amazon", "url": "https://amazon.com/dp/barbie-movie", "type": LinkType.STREAM},
            ],
        },
        "stranger things": {
            "title": "Stranger Things",
            "links": [
                {"label": "Watch on Netflix", "url": "https://netflix.com/title/80057281", "type": LinkType.STREAM},
            ],
        },
        "the last of us": {
            "title": "The Last of Us",
            "links": [
                {"label": "Watch on Max", "url": "https://max.com/series/the-last-of-us", "type": LinkType.STREAM},
                {"label": "Buy on Apple TV", "url": "https://tv.apple.com/show/the-last-of-us", "type": LinkType.BUY},
            ],
        },
    }

    async def find_streaming_links(
        self, title: str | None, description: str, detected_items: list[str], content_type: ContentType
    ) -> list[Link]:
        """Find streaming links for a movie or TV show."""
        search_text = " ".join([title or "", description, *detected_items]).lower()

        for keyword, media in self.MOCK_MOVIES.items():
            if keyword in search_text:
                logger.info("Matched media keyword: %s", keyword)
                return [Link(**link) for link in media["links"]]

        if title:
            encoded = quote(title.replace(" ", "+"))
            return [
                Link(
                    label=f"Search for '{title}' on JustWatch",
                    url=f"https://justwatch.com/us/search?q={encoded}",
                    type=LinkType.INFO,
                )
            ]

        return []
