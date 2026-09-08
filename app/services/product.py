import logging
from urllib.parse import quote

from app.schemas.pipeline import Link, LinkType

logger = logging.getLogger(__name__)


class ProductService:
    """Finds purchase links for detected products. Mock implementation for now."""

    MOCK_PRODUCTS: dict[str, dict] = {
        "dr martens": {
            "title": "Dr. Martens 1460 Pascal Virginia Boots",
            "links": [
                {"label": "Buy on Amazon", "url": "https://amazon.com/dp/B002B9K1XY", "type": LinkType.BUY},
                {"label": "Buy on DrMartens.com", "url": "https://drmartens.com/products/1460-pascal-virginia", "type": LinkType.BUY},
                {"label": "Buy on Zappos", "url": "https://zappos.com/p/dr-martens-1460-pascal", "type": LinkType.BUY},
            ],
        },
        "nike": {
            "title": "Nike Air Max 90",
            "links": [
                {"label": "Buy on Nike.com", "url": "https://nike.com/w/air-max-90", "type": LinkType.BUY},
                {"label": "Buy on Amazon", "url": "https://amazon.com/s?k=nike+air+max+90", "type": LinkType.BUY},
            ],
        },
        "ipad": {
            "title": "Apple iPad",
            "links": [
                {"label": "Buy on Apple", "url": "https://apple.com/shop/buy-ipad", "type": LinkType.BUY},
                {"label": "Buy on Amazon", "url": "https://amazon.com/s?k=apple-ipad", "type": LinkType.BUY},
            ],
        },
        "lego": {
            "title": "LEGO Set",
            "links": [
                {"label": "Buy on LEGO.com", "url": "https://lego.com", "type": LinkType.BUY},
                {"label": "Buy on Amazon", "url": "https://amazon.com/s?k=lego", "type": LinkType.BUY},
            ],
        },
    }

    async def find_buy_links(
        self, title: str | None, description: str, detected_items: list[str]
    ) -> list[Link]:
        """Find buy links for a product."""
        search_text = " ".join([title or "", description, *detected_items]).lower()

        for keyword, product in self.MOCK_PRODUCTS.items():
            if keyword in search_text:
                logger.info("Matched product keyword: %s", keyword)
                return [Link(**link) for link in product["links"]]

        if title:
            encoded = quote(title.replace(" ", "+"))
            return [
                Link(
                    label=f"Search for '{title}' on Amazon",
                    url=f"https://amazon.com/s?k={encoded}",
                    type=LinkType.BUY,
                )
            ]

        return []
