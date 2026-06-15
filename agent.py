"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json

from groq import Groq, BadRequestError
from tools import search_listings, suggest_outfit, create_fit_card, add_items_to_wardrobe
from config import MAX_TOOL_ROUNDS, LLM_MODEL, GROQ_API_KEY


def _get_groq_client():
    api_key = GROQ_API_KEY
    if not api_key:
        raise ValueError("GROQ_API_KEY not set. Add it to a .env file in the project root.")
    return Groq(api_key=api_key)


# ── Tool definitions ──────────────────────────────────────────────────────────
#
# Groq-compatible function schemas passed to the LLM so it can decide which
# tools to call and what arguments to supply.
#
# Argument-parsing notes per tool:
#   search_listings      — LLM must extract description/size/max_price from the query.
#   add_items_to_wardrobe — LLM must construct structured item dicts from the query.
#   suggest_outfit       — no LLM-parsed args; main loop supplies session state.
#   create_fit_card      — no LLM-parsed args; main loop supplies session state.

TOOLS_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_listings",
            "description": (
                "Search the thrift listings database for items matching the user's request. "
                "Call this tool whenever the user asks to find, search for, or browse items. "
                "Parse the following arguments directly from the user's query:\n"
                "  • description — extract keywords that describe what the user wants "
                "(style, item type, brand, color, material, aesthetic, etc.). "
                "Include all relevant descriptors; do NOT include size or price in this field.\n"
                "  • size — extract only if the user explicitly states a size "
                "(e.g. 'size M', 'XL', 'small'). Omit entirely if no size is mentioned.\n"
                "  • max_price — extract only if the user states a price ceiling "
                "(e.g. 'under $30', 'less than 50 dollars', 'max $25'). "
                "Return as a number (e.g. 30.0). Omit entirely if no price limit is mentioned."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": (
                            "Keywords describing what the user is looking for "
                            "(e.g. 'vintage graphic tee', 'oversized denim jacket'). "
                            "Do not include size or price."
                        ),
                    },
                    "size": {
                        "type": ["string", "null"],
                        "description": (
                            "Size string to filter by, exactly as the user stated it "
                            "(e.g. 'M', 'L', 'XL', 'S/M'). Omit if not mentioned."
                        ),
                    },
                    "max_price": {
                        "type": ["number", "null"],
                        "description": (
                            "Maximum price the user is willing to pay, as a float "
                            "(e.g. 30.0). Omit if the user did not state a price limit."
                        ),
                    },
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_items_to_wardrobe",
            "description": (
                "Add one or more clothing items to the user's wardrobe. "
                "Call this tool when the user describes pieces they already own, "
                "says they want to add items to their wardrobe, or provides wardrobe context "
                "(e.g. 'I have baggy jeans and chunky sneakers'). "
                "Parse each item the user mentions into a structured dict using the wardrobe schema:\n"
                "  • id — generate a short unique string (e.g. 'u_001', 'u_002').\n"
                "  • name — a short descriptive label for the piece (e.g. 'baggy jeans').\n"
                "  • category — one of: tops, bottoms, outerwear, shoes, accessories.\n"
                "  • colors — list of colors mentioned or implied; use an empty list if unknown.\n"
                "  • style_tags — list of style descriptors inferred from the description "
                "(e.g. ['streetwear', 'oversized']); use an empty list if none apply.\n"
                "  • notes — any extra fit or styling detail the user mentions; omit this field entirely if none apply."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "items_to_add": {
                        "type": "array",
                        "description": "List of wardrobe item dicts to add.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "Unique identifier (e.g. 'u_001').",
                                },
                                "name": {
                                    "type": "string",
                                    "description": "Short label for the item (e.g. 'baggy jeans').",
                                },
                                "category": {
                                    "type": "string",
                                    "enum": ["tops", "bottoms", "outerwear", "shoes", "accessories"],
                                    "description": "Item category.",
                                },
                                "colors": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Colors present in the item.",
                                },
                                "style_tags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Style descriptors for the item.",
                                },
                                "notes": {
                                    "type": ["string", "null"],
                                    "description": "Optional fit or styling notes.",
                                },
                            },
                            "required": ["id", "name", "category", "colors", "style_tags"],
                        },
                    },
                },
                "required": ["items_to_add"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_outfit",
            "description": (
                "Suggest 1–2 complete outfits built around a thrifted item the user is considering. "
                "IMPORTANT: Only call this tool after search_listings has successfully returned results "
                "and a selected item is available. Do NOT call this tool if search_listings has not run "
                "yet or returned an empty result — there is no item to style. "
                "No arguments are required; the main loop supplies the selected item and wardrobe automatically."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_fit_card",
            "description": (
                "Generate a short, shareable OOTD-style social media caption for the thrifted find. "
                "IMPORTANT: Only call this tool after search_listings has successfully returned results "
                "and a selected item is available. Do NOT call this tool if search_listings has not run "
                "yet or returned an empty result — a caption cannot be created without a listing. "
                "No arguments are required; the main loop supplies the outfit suggestion and selected item automatically."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are FitFindr, an AI thrift-shopping assistant. Your job is to help users \
find second-hand clothing, build outfits around their finds, and create shareable social media \
captions — always by calling the tools provided. Never answer from your own general knowledge \
when a tool exists for the task.

## Tool orchestration

Follow this sequence for every query:

1. If the user describes clothing they already own or asks to add items to their wardrobe, \
call `add_items_to_wardrobe` to record those pieces before searching.

2. Call `search_listings` to find matching thrift items. Extract `description`, and — only if \
explicitly stated by the user — `size` and `max_price`.

3. Call `suggest_outfit` ONLY after `search_listings` has successfully returned a result. \
Do NOT call it if no listing was found. No arguments are needed — the loop supplies the \
selected item and wardrobe automatically from session state.

4. Call `create_fit_card` ONLY after both `search_listings` and `suggest_outfit` have run \
successfully. Do NOT call it if no listing was found. No arguments are needed — the loop \
supplies the outfit suggestion and selected item automatically from session state.

## Error handling

**Critical — search returns no results:**
If `search_listings` returns an empty result, stop immediately. Do not call any other tools.

**Soft — `add_items_to_wardrobe` fails:**
If `add_items_to_wardrobe` returns an error string (i.e. no items were saved), do not stop — \
continue with the rest of the flow. If `suggest_outfit` subsequently returns no output or the \
outfit suggestion is empty at the end of the loop, your final text response should acknowledge \
that wardrobe items could not be saved and provide general styling advice based on the selected \
item and any style preferences mentioned in the user's query. This response will be displayed in \
the "Outfit idea" panel. This is the only situation where you may draw on general fashion \
knowledge instead of tool output.

**Soft — `suggest_outfit` has no wardrobe to work with:**
If the wardrobe is empty, `suggest_outfit` will return general styling advice rather than \
wardrobe-specific outfit combinations — that output is still valid. Call `create_fit_card` \
after it completes; the loop will supply the result automatically.

**Soft — `create_fit_card` receives incomplete outfit input:**
If called with an empty outfit, the tool will return an error string. If this error occurs, \
your final text response must handle the fallback by generating a social media caption natively \
in your conversational output to populate the panel, basing the caption on the details of the selected_item \
and any style keywords from the user's query. Make it sound like a real OOTD post — casual, authentic, \
and specific about the vibe. Mention the item name, price, and platform naturally (once each).

Dual Fallback Formatting Rules:
If a pipeline failure forces you to generate BOTH the styling advice and the social media caption natively \
in your final text response, you MUST separate them cleanly using the tokens [OUTFIT] and [CAPTION].
Example format:
[OUTFIT]
General styling advice goes here...
[CAPTION]
Your creative social media caption goes here...

## General guidance

- Respect tool dependencies: Only trigger dependent tools (like styling or captions) if their exact prerequisites \
successfully returned data in a previous turn. Skip tools entirely if their prerequisites failed or are irrelevant to the user's intent.
- Do not call `suggest_outfit` or `create_fit_card` more than once per turn.
- All output surfaces through session state displayed in three UI panels — there is no chat \
window. Your final text response is only used as a fallback to populate a panel when a tool \
could not produce output.
- If the user's query does not require any tool (e.g. a general fashion question with no item \
to find), answer with a short plain-text response.
"""


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def _strip_nulls(obj: dict) -> dict:
    result = {}
    for k, v in obj.items():
        if v is None:
            continue
        if isinstance(v, dict):
            result[k] = _strip_nulls(v)
        elif isinstance(v, list):
            result[k] = [_strip_nulls(i) if isinstance(i, dict) else i for i in v]
        else:
            result[k] = v
    return result

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """
    session = _new_session(query, wardrobe)
    client = _get_groq_client()

    messages: list = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]

    # Planning loop: keep calling the LLM until it stops requesting tool calls
    for _ in range(MAX_TOOL_ROUNDS):
        response = None
        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=messages,
                    tools=TOOLS_DEFINITIONS,  # type: ignore[arg-type]
                    tool_choice="auto",
                )
                break
            except BadRequestError as e:
                print(f"\n[RETRY {attempt + 1}/3] BadRequestError: {e}")
                if attempt == 2:
                    raise
        assert response is not None
        assistant_message = response.choices[0].message

        # Convert to a plain dict so it round-trips cleanly back into the messages list
        messages.append(assistant_message.model_dump(exclude_none=True))

        # No more tool calls — loop is done
        if not assistant_message.tool_calls:
            content = assistant_message.content
            # Check if the LLM packaged both fallbacks using tags
            if "[OUTFIT]" in content and "[CAPTION]" in content:    # type: ignore
                # Split the text at the [CAPTION] marker
                parts = content.split("[CAPTION]")                  # type: ignore
                outfit_text = parts[0].replace("[OUTFIT]", "").strip()
                caption_text = parts[1].strip() if len(parts) > 1 else ""

                if not session["outfit_suggestion"]:
                    session["outfit_suggestion"] = outfit_text
                if not session["fit_card"]:
                    session["fit_card"] = caption_text
            else:
                # Generic fallback if only one panel was empty
                if not session["outfit_suggestion"]:
                    session["outfit_suggestion"] = content
                if not session["fit_card"]:
                    session["fit_card"] = content
            break

        # Process each tool call in this turn
        for tool_call in assistant_message.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments or "{}") or {}
            args = _strip_nulls(args)

            print(f"\n{'='*60}")
            print(f"[TOOL CALL] {name}")

            if name == "search_listings":
                print(f"  [ARG SOURCE] description → LLM  | value: {args['description']!r}")
                print(f"  [ARG SOURCE] size        → LLM  | value: {args.get('size')!r}")
                print(f"  [ARG SOURCE] max_price   → LLM  | value: {args.get('max_price')!r}")

                results = search_listings(
                    description=args["description"],
                    size=args.get("size"),
                    max_price=args.get("max_price"),
                )
                session["search_results"] = results

                if not results:
                    session["error"] = (
                        "I couldn't find any listings that matched your search. Try rephrasing \
                        your description or removing size/price filters."
                    )
                    tool_result = session["error"]
                else:
                    session["selected_item"] = results[0]
                    item = results[0]
                    tool_result = (
                        f"Found item: '{item['title']}' — {item['description']} "
                        f"(${item['price']:.2f}, size {item['size']}, {item['platform']})"
                    )

                print(f"  [RESULT] {tool_result}")

            elif name == "add_items_to_wardrobe":
                print(f"  [ARG SOURCE] items_to_add → LLM  | value: {args.get('items_to_add')!r}")

                result = add_items_to_wardrobe(
                    items_to_add=args.get("items_to_add", []),
                    wardobe=session["wardrobe"],
                )
                if isinstance(result, str):
                    # Error string returned — soft failure, continue
                    tool_result = result
                else:
                    added = ", ".join(f"{n} ({cat})" for n, cat in result)
                    tool_result = f"Added {len(result)} item(s) to wardrobe: {added}"

                print(f"  [RESULT] {tool_result}")

            elif name == "suggest_outfit":
                print(f"  [ARG SOURCE] new_item → session['selected_item'] | value: {session['selected_item']!r}")
                print(f"  [ARG SOURCE] wardrobe → session['wardrobe']       | keys: {list(session['wardrobe'].keys()) if isinstance(session['wardrobe'], dict) else type(session['wardrobe'])}")

                if session["selected_item"] is None:
                    tool_result = "Error: no item selected — search_listings must run first."
                else:
                    outfit = suggest_outfit(
                        new_item=session["selected_item"],
                        wardrobe=session["wardrobe"],
                    )
                    session["outfit_suggestion"] = outfit
                    tool_result = outfit

                print(f"  [RESULT] {tool_result}")

            elif name == "create_fit_card":
                print(f"  [ARG SOURCE] outfit   → session['outfit_suggestion'] | value: {session['outfit_suggestion']!r}")
                print(f"  [ARG SOURCE] new_item → session['selected_item']     | value: {session['selected_item']!r}")

                if session["selected_item"] is None:
                    tool_result = "Error: no item selected — search_listings must run first."
                else:
                    caption = create_fit_card(
                        outfit=session["outfit_suggestion"] or "",
                        new_item=session["selected_item"],
                    )
                    if caption.startswith("Error:"):
                        # Log the error to message history so the LLM knows it failed
                        tool_result = caption 

                    # Do NOT populate session["fit_card"] with the error string
                    else:
                        session["fit_card"] = caption
                        tool_result = caption

                print(f"  [RESULT] {tool_result}")

            else:
                tool_result = f"Unknown tool: {name}"
                print(f"  [RESULT] {tool_result}")

            print(f"{'='*60}")

            # Append the tool result to history
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            })

        # Critical error: stop the loop if search returned nothing
        if session["error"]:
            break

    else:
        session["error"] = (
            f"I wasn't able to complete your request within {MAX_TOOL_ROUNDS} steps. "
            "I'm here to help you find thrifted items and build outfits — try rephrasing your query!"
        )

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
    print(session2)
