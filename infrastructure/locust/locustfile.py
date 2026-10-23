"""Locust Load Generation Script for Online Boutique Cloud-Native Testbed.

Simulates realistic microservice user behavior:
1. Home page browsing
2. Viewing products from catalog
3. Changing currency
4. Adding items to cart
5. Checking out order
"""

import random
from locust import HttpUser, between, task

PRODUCT_IDS = [
    "0PUK6V6EV0",  # Vintage Typewriter
    "1YMWWN1N4O",  # Home Barista Kit
    "2ZYFJ3GM2N",  # Film Camera
    "66VCHSJNUP",  # Vintage Record Player
    "6E92ZMYY0V",  # Terrarium
    "L9ECAV7KIM",  # Loafers
    "OLJCESPC7Z",  # Bamboo Glass Jar
]

CURRENCIES = ["USD", "EUR", "JPY", "GBP", "CAD"]


class BoutiqueShopper(HttpUser):
    """Simulates realistic end-user shopping workflow on Online Boutique."""

    wait_time = between(1, 3)

    @task(10)
    def index(self) -> None:
        """Browse the storefront home page."""
        self.client.get("/", name="Browse Home")

    @task(8)
    def view_product(self) -> None:
        """Inspect product details."""
        pid = random.choice(PRODUCT_IDS)
        self.client.get(f"/product/{pid}", name="View Product")

    @task(3)
    def switch_currency(self) -> None:
        """Switch display currency."""
        curr = random.choice(CURRENCIES)
        self.client.post("/setCurrency", data={"currency_code": curr}, name="Set Currency")

    @task(5)
    def add_to_cart(self) -> None:
        """Add a product to cart."""
        pid = random.choice(PRODUCT_IDS)
        qty = random.randint(1, 3)
        self.client.post(
            "/cart",
            data={"product_id": pid, "quantity": qty},
            name="Add to Cart",
        )

    @task(3)
    def view_cart(self) -> None:
        """Inspect current shopping cart."""
        self.client.get("/cart", name="View Cart")

    @task(2)
    def checkout(self) -> None:
        """Complete purchase and trigger checkout flow across downstream services."""
        # First ensure item in cart
        pid = random.choice(PRODUCT_IDS)
        self.client.post(
            "/cart",
            data={"product_id": pid, "quantity": 1},
            name="Checkout - Preload Cart",
        )
        self.client.post(
            "/cart/checkout",
            data={
                "email": "test-shopper@example.com",
                "street_address": "1600 Amphitheatre Pkwy",
                "zip_code": "94043",
                "city": "Mountain View",
                "state": "CA",
                "country": "United States",
                "credit_card_number": "4111111111111111",
                "credit_card_expiration_month": "12",
                "credit_card_cvv": "123",
            },
            name="Checkout Order",
        )
