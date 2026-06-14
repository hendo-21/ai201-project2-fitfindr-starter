"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # Filter by price and size
    filtered = []
    for listing in listings:
        if max_price is not None and listing["price"] > max_price:
            continue
        if size is not None and size.lower() not in listing["size"].lower():
            continue
        filtered.append(listing)

    # Score by keyword overlap with description
    keywords = description.lower().split()
    scored = []
    for listing in filtered:
        searchable = " ".join([
            listing["title"],
            listing["description"],
            listing["category"],
            " ".join(listing["style_tags"]),
            " ".join(listing["colors"]),
            listing["brand"] or "",
        ]).lower()
        score = sum(1 for kw in keywords if kw in searchable)
        if score > 0:
            scored.append((score, listing))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [listing for _, listing in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    client = _get_groq_client()
    wardrobe_items = wardrobe.get("items", [])

    item_summary = (
        f"{new_item['title']} — {new_item['description']} "
        f"(colors: {', '.join(new_item['colors'])}, style: {', '.join(new_item['style_tags'])})"
    )

    if not wardrobe_items:
        prompt = (
            f"I'm considering buying this thrifted item: {item_summary}\n\n"
            "I don't have any wardrobe info on file yet. "
            "Please suggest what kinds of pieces pair well with it and what overall vibe or aesthetic it suits. "
            "Give 1 to 2 outfit ideas, with each outfit described in 1 sentence."
        )
    else:
        wardrobe_lines = "\n".join(
            f"- {item['name']} ({item['category']}): colors={', '.join(item.get('colors', []))}, "
            f"style={', '.join(item.get('style_tags', []))}"
            for item in wardrobe_items
        )
        prompt = (
            f"I'm considering buying this thrifted item: {item_summary}\n\n"
            f"Here's what I already own:\n{wardrobe_lines}\n\n"
            "Using the new item and specific pieces from my wardrobe, suggest 1 to 2 complete outfits. "
            "Name the specific wardrobe pieces in each outfit. Describe each outfit in 1 sentence. "
            "Only include a second outfit if it uses entirely different wardrobe pieces than the first — do not reuse any wardrobe item across both outfits."
        )

    system_prompt = (
        "You are a friendly personal stylist who specializes in thrift fashion. "
        "Output only the outfit sentences — no labels, numbers, preamble, or explanation. "
        "A second outfit is only valid if it draws on a completely different set of wardrobe pieces than the first. "
        "If the wardrobe does not have enough distinct pieces to build two outfits with non-overlapping wardrobe items, return exactly one outfit and stop."
    )
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    )
    raw = response.choices[0].message.content

    # Strip any leading label the LLM adds despite the instruction, e.g.
    # "Outfit 1: ...", "1. ...", "Here are two outfits: ..."
    # Targets only labels at the start of a line, so colons inside
    # outfit descriptions are preserved.
    label_pattern = re.compile(
        r"^\s*(outfit\s*\d+|here\b[^:]*|\d+\.?)\s*:?\s*",
        re.IGNORECASE,
    )
    sentences = []
    for line in raw.splitlines():   # type: ignore
        line = label_pattern.sub("", line).strip()
        if line:
            sentences.append(line)
    return " ".join(sentences)


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    client = _get_groq_client()

    item_summary = (
        f"{new_item['title']} — {new_item['description']} "
        f"(colors: {', '.join(new_item['colors'])}, style: {', '.join(new_item['style_tags'])}, "
        f"${new_item['price']:.2f} on {new_item['platform']})"
    )

    if not outfit or not outfit.strip():
        prompt = (
            f"Write a 2–4 sentence Instagram caption for this thrifted find: {item_summary}\n\n"
            "Make it sound like a real OOTD post — casual, authentic, and specific about the vibe. "
            "Mention the item name, price, and platform naturally (once each)."
        )
    else:
        prompt = (
            f"Write a 2–4 sentence Instagram caption for this thrifted find: {item_summary}\n\n"
            f"The outfit I'm wearing it with: {outfit}\n\n"
            "Make it sound like a real OOTD post — casual, authentic, and specific about the vibe. "
            "Mention the item name, price, and platform naturally (once each)."
        )

    system_prompt = (
        "You are a fashion-forward thrift shopper writing OOTD captions for Instagram and TikTok. "
        "Write in first person, keep it casual and genuine — not promotional. "
        "Output only the caption text, no hashtags, no labels, no preamble."
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=1.2,
    )
    return (response.choices[0].message.content or "").strip()

# ── Tool 4: add_items_to_wardrobe ─────────────────────────────────────────────
def add_items_to_wardrobe(items_to_add: list, wardobe: dict) -> list | str:
    """
    Adds the list of wardrobe items to the wardrobe.

    Args:
        items_to_add: A list of wardrobe items formatted according to the schema["items"][0] in wardrobe_schema.json.
        wardrobe: The session's wardrobe dict. wardrobe["items"] contains the list of items in the wardrobe.

    Returns:
        A list of tuples where each tuple contains the item name and category:
            (str: <item name>, str: <category>) -> ("baggy jeans", "bottoms"). 
        If no items were added, an error string stating there was a parsing error.

    TODO:
        1. Append the items to the wardrobe.
        2. Parse the item name and category for each item in items_to_add and format the return string.
    """
    if not items_to_add:
        return "Error: Could not save items to wardrobe state."

    wardobe["items"].extend(items_to_add)

    return [(item["name"], item["category"]) for item in items_to_add]
