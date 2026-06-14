import unittest
from unittest.mock import MagicMock, patch

from tools import search_listings, suggest_outfit, create_fit_card, add_items_to_wardrobe


# ── Helper ────────────────────────────────────────────────────────────────────

def _mock_groq_response(text):
    """Return a MagicMock shaped like a Groq ChatCompletion response."""
    message = MagicMock()
    message.content = text
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


# ── Fixtures pulled from listings.json and wardrobe_schema.json ───────────────

# lst_006: Graphic Tee — 2003 Tour Bootleg Style (size L, $24, streetwear/vintage)
GRAPHIC_TEE = {
    "id": "lst_006",
    "title": "Graphic Tee — 2003 Tour Bootleg Style",
    "description": "Vintage-style bootleg tee with faded graphic. Slightly boxy fit. 100% cotton, soft and worn-in.",
    "category": "tops",
    "style_tags": ["graphic tee", "vintage", "grunge", "streetwear", "band tee"],
    "size": "L",
    "condition": "good",
    "price": 24.00,
    "colors": ["black"],
    "brand": None,
    "platform": "depop",
}

# Two wardrobe items — small enough that the LLM should return only 1 outfit
SMALL_WARDROBE = {
    "items": [
        {
            "id": "w_001",
            "name": "Baggy straight-leg jeans, dark wash",
            "category": "bottoms",
            "colors": ["dark blue", "indigo"],
            "style_tags": ["denim", "streetwear", "baggy"],
            "notes": "High-waisted, sits above the hip",
        },
        {
            "id": "w_007",
            "name": "Chunky white sneakers",
            "category": "shoes",
            "colors": ["white"],
            "style_tags": ["sneakers", "chunky", "streetwear"],
            "notes": None,
        },
    ]
}

# Five wardrobe items — enough variety that the LLM could return 1–2 outfits
LARGE_WARDROBE = {
    "items": [
        {
            "id": "w_001",
            "name": "Baggy straight-leg jeans, dark wash",
            "category": "bottoms",
            "colors": ["dark blue", "indigo"],
            "style_tags": ["denim", "streetwear", "baggy"],
            "notes": None,
        },
        {
            "id": "w_002",
            "name": "Wide-leg khaki trousers",
            "category": "bottoms",
            "colors": ["khaki", "tan"],
            "style_tags": ["earth tones", "minimal", "wide-leg"],
            "notes": None,
        },
        {
            "id": "w_007",
            "name": "Chunky white sneakers",
            "category": "shoes",
            "colors": ["white"],
            "style_tags": ["sneakers", "chunky", "streetwear"],
            "notes": None,
        },
        {
            "id": "w_008",
            "name": "Black combat boots",
            "category": "shoes",
            "colors": ["black"],
            "style_tags": ["boots", "grunge", "classic"],
            "notes": "Lace-up, mid-ankle height",
        },
        {
            "id": "w_006",
            "name": "Vintage black denim jacket",
            "category": "outerwear",
            "colors": ["black"],
            "style_tags": ["denim", "vintage", "classic"],
            "notes": "Slightly cropped",
        },
    ]
}

EMPTY_WARDROBE = {"items": []}


# ── Test search_listings ──────────────────────────────────────────────────────

class TestSearchListings(unittest.TestCase):

    def test_returns_results_no_filters(self):
        """Keyword search with no filters returns at least one matching listing."""
        results = search_listings("vintage graphic tee")
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

    def test_returns_results_max_price_filter(self):
        """All returned listings are at or below max_price."""
        results = search_listings("vintage", max_price=20.00)
        self.assertGreater(len(results), 0)
        for item in results:
            self.assertLessEqual(item["price"], 20.00)

    def test_returns_results_size_filter(self):
        """All returned listings contain the requested size string."""
        # "vintage" matches many listings; size "M" filters to items whose
        # size field contains "m" (e.g. "M", "S/M", "M/L").
        results = search_listings("vintage", size="M")
        self.assertGreater(len(results), 0)
        for item in results:
            self.assertIn("m", item["size"].lower())

    def test_returns_results_both_filters(self):
        """Combining size and max_price filters works correctly together."""
        results = search_listings("top", size="S", max_price=25.00)
        for item in results:
            self.assertIn("s", item["size"].lower())
            self.assertLessEqual(item["price"], 25.00)

    def test_no_match_returns_empty_list(self):
        """A description with no keyword overlap returns an empty list, not an error."""
        results = search_listings("zzzzunmatchablezzzz")
        self.assertEqual(results, [])


# ── Test suggest_outfit ───────────────────────────────────────────────────────

class TestSuggestOutfit(unittest.TestCase):

    @patch("tools._get_groq_client")
    def test_small_wardrobe_returns_one_sentence(self, mock_get_client):
        """
        With only 2 wardrobe items the LLM cannot build two non-overlapping
        outfits, so the result should be a single sentence.
        """
        mock_get_client.return_value.chat.completions.create.return_value = (
            _mock_groq_response(
                "Style the graphic tee with baggy jeans and chunky white sneakers for a streetwear look."
            )
        )
        result = suggest_outfit(GRAPHIC_TEE, SMALL_WARDROBE)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)
        # A single sentence ends with one terminal punctuation mark
        sentences = [s.strip() for s in result.split(".") if s.strip()]
        self.assertEqual(len(sentences), 1)

    @patch("tools._get_groq_client")
    def test_large_wardrobe_returns_one_or_two_sentences(self, mock_get_client):
        """With 5 wardrobe items the LLM may return 1–2 outfit sentences."""
        mock_get_client.return_value.chat.completions.create.return_value = (
            _mock_groq_response(
                "Wear the graphic tee with baggy jeans and chunky sneakers for a casual streetwear look. "
                "Swap in the wide-leg trousers and combat boots with the denim jacket for a grungier vibe."
            )
        )
        result = suggest_outfit(GRAPHIC_TEE, LARGE_WARDROBE)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)
        sentences = [s.strip() for s in result.split(".") if s.strip()]
        self.assertIn(len(sentences), [1, 2])

    @patch("tools._get_groq_client")
    def test_empty_wardrobe_returns_general_styling_advice(self, mock_get_client):
        """
        Failure mode: empty wardrobe.
        suggest_outfit must return a non-empty string with general styling advice
        rather than raising an exception.
        """
        mock_get_client.return_value.chat.completions.create.return_value = (
            _mock_groq_response(
                "This vintage graphic tee pairs well with wide-leg trousers and chunky sneakers for a relaxed streetwear look."
            )
        )
        result = suggest_outfit(GRAPHIC_TEE, EMPTY_WARDROBE)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)


# ── Test create_fit_card ──────────────────────────────────────────────────────

class TestCreateFitCard(unittest.TestCase):

    @patch("tools._get_groq_client")
    def test_valid_outfit_returns_caption(self, mock_get_client):
        """A valid outfit string and listing produce a non-empty caption string."""
        mock_get_client.return_value.chat.completions.create.return_value = (
            _mock_groq_response(
                "Thrifted this Graphic Tee for $24 on depop and I'm obsessed. "
                "The baggy jeans and chunky sneakers complete the look perfectly."
            )
        )
        result = create_fit_card(
            "Baggy jeans and chunky sneakers.", GRAPHIC_TEE
        )
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    @patch("tools._get_groq_client")
    def test_empty_outfit_string_returns_item_only_caption(self, mock_get_client):
        """
        Failure mode: empty outfit string.
        create_fit_card falls back to a caption based on the item alone
        and does NOT raise an exception.
        """
        mock_get_client.return_value.chat.completions.create.return_value = (
            _mock_groq_response(
                "Found this Graphic Tee for $24 on depop and couldn't leave it behind."
            )
        )
        result = create_fit_card("", GRAPHIC_TEE)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    @patch("tools._get_groq_client")
    def test_whitespace_only_outfit_returns_item_only_caption(self, mock_get_client):
        """
        Failure mode: whitespace-only outfit string.
        The function treats it the same as an empty string and returns a caption
        without raising.
        """
        mock_get_client.return_value.chat.completions.create.return_value = (
            _mock_groq_response(
                "Just copped this vintage graphic tee for $24 — thrift finds hit different."
            )
        )
        result = create_fit_card("   ", GRAPHIC_TEE)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)


# ── Test add_items_to_wardrobe ────────────────────────────────────────────────

class TestAddItemsToWardrobe(unittest.TestCase):

    def setUp(self):
        """Each test gets a fresh empty wardrobe so mutations don't bleed between tests."""
        self.wardrobe = {"items": []}

    def test_empty_items_list_returns_error_string(self):
        """
        Failure mode: no items provided.
        The function returns the designated error string instead of raising.
        """
        result = add_items_to_wardrobe([], self.wardrobe)
        self.assertIsInstance(result, str)
        self.assertIn("Error", result)

    def test_adds_three_items_returns_name_category_tuples(self):
        """
        Three wardrobe items (derived from listings.json entries) are added
        and the function returns a list of (name, category) tuples.
        """
        # These items are formatted to match the wardrobe schema items format.
        items_to_add = [
            {
                "id": "w_new_001",
                "name": "Graphic Tee — 2003 Tour Bootleg Style",
                "category": "tops",
                "colors": ["black"],
                "style_tags": ["graphic tee", "vintage", "streetwear"],
                "notes": None,
            },
            {
                "id": "w_new_002",
                "name": "Vintage Levi's 501 Jeans — Medium Wash",
                "category": "bottoms",
                "colors": ["blue", "indigo"],
                "style_tags": ["vintage", "denim", "streetwear"],
                "notes": None,
            },
            {
                "id": "w_new_003",
                "name": "90s Track Jacket — Navy/White Stripe",
                "category": "outerwear",
                "colors": ["navy", "white"],
                "style_tags": ["90s", "vintage", "athletic"],
                "notes": None,
            },
        ]

        result = add_items_to_wardrobe(items_to_add, self.wardrobe)

        # Returns a list of (name, category) tuples
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], ("Graphic Tee — 2003 Tour Bootleg Style", "tops"))
        self.assertEqual(result[1], ("Vintage Levi's 501 Jeans — Medium Wash", "bottoms"))
        self.assertEqual(result[2], ("90s Track Jacket — Navy/White Stripe", "outerwear"))

        # The wardrobe is also updated in place
        self.assertEqual(len(self.wardrobe["items"]), 3)


if __name__ == "__main__":
    unittest.main()