# FitFindr — Project 2

FitFinder is a multi-tool AI agent that helps users find secondhand pieces, figure out how to style them, and generate an OOTD style caption for their socials. The agent uses the ReAct framework.

---

## Tool Inventory

### Tool 1: search_listings

**What it does:**
Searches the listings data for items matching the description, size, and within the bounds set by the max price. Size and max price are both optional and default to None if not provided.

**Input parameters:**
- `description` (str): Keywords describing what the user is looking for.
- `size` (str): A size string to filter listings by. None if not provided.
- `max_price` (float): The maximum price (inclusive) is looking to pay to filter listings by. None if not provided.

**What it returns:**
The function returns a list of matching listing dicts based on the input parameters. The list is sorted from most relevant to least. 

**What happens if it fails or returns nothing:**
If no listings match, the function will return an empty list. The agent should inform the user that it could not find relevant listings based on the provided description, size, or price (if they were provided), and suggest that the user try re-phrasing their description, and/or provide additional details.

---

### Tool 2: suggest_outfit

**What it does:**
The function takes a an item the user is considering buying, the user's wardrobe, and suggests 1-2 complete outfits. 

**Input parameters:**
- `new_item` (dict): A listing from the listings database representing an item the user wants to buy.
- `wardrobe` (dict): A dict with a key "items", which contains a list of wardrobe item dicts. May be empty.

**What it returns:**
A non-empty string containing the outfit suggestions based on either the `new_item` and the `wardrobe`, or general styling based on `new_item` if no wardrobe is found.

**What happens if it fails or returns nothing:**
If the wardrobe is empty or no outfit can be suggested, the agent should check the initial query to see if it included style preferences, and then offer styling advice based on that. If the initial query did not include any style preferences, then offer general styling advice based on `new_item`. The agent should also offer to add wardrobe pieces, providing the user with details on the information needed to fill out a wardrobe item (wardrobe-schema in human readable format).

---

### Tool 3: create_fit_card

**What it does:**
Generates a 2-4 sentence outfit-of-the-day style caption for social media based on the suggested outfit and thrifted find.

**Input parameters:**
- `outfit` (str): The outfit suggestions returned by `suggest_outfit` 
- `new_item` (dict): A listing from the listings database representing an item the user wants to buy.

**What it returns:**
A 2-4 sentence string that can be used on TikTok/Instagram.

**What happens if it fails or returns nothing:**
The agent should tell the user that the outfit data is incomplete, and then provide a caption based on the thrifted item only.

---

### Tool 4: add_items_to_wardrobe

**What it does:**
Adds one or more items to the user's session wardrobe.

**Input parameters:**
- `items_to_add` (list[dict]): A list of structured dict objects matching the wardrobe schema (name, category, colors, style_tags, notes).
- `wardrobe'` (list[dict]): The active session wardrobe list, passed by reference and modified in-place.

**What it returns:**
A string containing a success message that includes number of pieces added. If there was an error and nothing could be added, a error string stating nothing was added is returned.

**What happens if it fails or returns nothing:**
It returns a string describing the failure: "Error: Could not save items to wardrobe state."

---

### Error handling strategy

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Critical error: exit the agent loop and return a helpful message to the user on how they can update their query to generate results. |
| suggest_outfit | Wardrobe is empty | Provide general styling advice based on the `selected_item`. |
| create_fit_card | Outfit input is missing or incomplete | Create a caption based on the `selected_item` and query context. |
| add_items_to_wardrobe | No items added to wardrobe | Provide general styling advice based on related descriptions provided and `selected_item`. |

**Error handling agent response examples**

Scenario: the user enters a query that generates no search listings.
- Agent response: exit the planning loop early and provide the user with a helpful message about what went wrong and how to retry with a better query.
- Evidence: [Gradio UI screenshot showing agent response](images/gradio-no-search-results.png) | [Terminal screenshot showing search_listing returns empty list and doesn't raise exception](images/search-listings-no-results.png)

Scenario: `suggest_outfit` is triggered with an empty wardrobe.
- Agent response: the tool returns a helpful string with general styling advice rather than raising an exception or returning an empty string.
- Evidence: [Terminal screenshot showing helpul string response](images/suggest-outfit-empty-wardrobe.png)

Scenario: `create_fit_card` is triggered with an empty outfit string.
- Agent response: the tool returns a descriptive error message string and the agent generates a caption based on query context and `selected_item`, which gets stored in `session["fit_card"].
- Evidence: [Gradio UI screenshot showing agent response](images/gradio-create-fit-card-empty-outfit-suggestion.png) | [Terminal screenshot showing `create_fit_card` returns an error string](images/create-fit-card-empty-outfit-suggestion.png)

---

## The Planning Loop

The agent receives system prompt, user query, and a list of messages containing the turn history, including the tools called and the tool-call results. The agent makes an initial call to the LLM—including the user's query, a system prompt, and tool definitions—to determine which tools need to be called.

The agent then executes a dynamic orchestrator loop governed by the following conditional branching logic:

**Loop Condition (while tools are requested):** As long as the LLM's response contains a tool_calls array, the execution loop continues turn-by-turn.
* If the requested tool needs to parse information from the user query (search_listings or add_items_to_wardrobe), the agent extracts the tool name and arguments natively parsed by the LLM.
* If the tool does not require arguments from the LLM (suggest_outfit or create_fit_card), the agent bypasses LLM parsing and uses arguments directly from the backend session state for the tool call.
* If a tool call sets a critical "error" attribute in the session object, the main loop catches this flag immediately after execution, breaks the loop, and exits early.

Session object attributes are updated deterministically after tool results are retured to the main loop. Before moving to the next turn, the full assistant message and the tool-call result are appended to the messages history.

When the LLM emits a response with no more tools to call, the loop completes. The agent captures the LLM's final conversational message content, assigns it to the appropriate session attributes to handle soft fallbacks if necessary (applicable for `add_items_to_wardrobe` only), and returns the session object.

---

**Architecture**
```
User query
    │
    ▼
Planning Loop ────────────────────────────────────────────────────────┐
    │                                                                 │
    ├─► add_items_to_wardrobe(items_to_add, wardrobe)                 │
    │       │                                                         │
    │       ├──► [FALLBACK] No items added      ──────────────────────┤
    │       │    (Loop continues; Final handoff catches this later    │
    │       │     to provide text styling advice)                     │
    │       │                                                         │
    │       ▼                                                         │
    │   Session: wardrobe list updated (if items successfully parsed) │
    │       │                                                         │
    ├─► search_listings(description, size, max_price)                 │
    │       │                                                         │
    │       ├──► [CRITICAL ERROR] No results match ───────────────────│
    │       │    (Sets session["error"] to inform user and suggest    │
    │       │     providing greater detail or removing filters)       │
    │       │                                                         │
    │       │ results=[item, ...]                                     │
    │       ▼                                                         │
    │   Session: selected_item = results[0]                           │
    │       │                                                         │
    ├─► suggest_outfit(selected_item, wardrobe)                       │
    │       │                                                         │
    │       ├──► [FALLBACK] Wardrobe is empty                         │
    │       │    (Session: outfit_suggestion = general styling        │
    │       │     advice based entirely on the selected_item)         │
    │       │                                                         │
    │       ▼                                                         │
    │   Session: outfit_suggestion = "..."                            │
    │       │                                                         │
    └─► create_fit_card(outfit_suggestion, selected_item)             │
            │                                                         │
            ├──► [FALLBACK] Outfit input missing/incomplete           │ 
            │    (Session: fit_card = caption generated using         │
            │     the selected_item descriptors alone)                │
            │                                                         │
            ▼                                                         │
        Session: fit_card = "..."                                     │
            │                                                         └─ Critical error exit early
            ▼
    Final Handoff: If outfit_suggestion is still completely empty 
    (due to a wardrobe addition failure), populate it with the 
    LLM's conversational text response explaining the issue + 
    providing fallback styling advice.
            │
            ▼
      Return session
```

---

### State Management Approach
State is managed through a hybrid approach: the conversational history (messages list) maintains the agent's logical memory, while the backend session dictionary handles the physical data transmission. While the actual content returned by the tools is used to update session attributes, tool results appended to the messages list are either context-rich summary strings or the literal text outputs of the tools. Summary strings are used for `search_listings` and `add_item_to_wardobe`, and the literal text outputs are used for `suggest_outfit` and `create_fit_card`. This allows the agent to track the tool execution history to determine if the tools have the pre-requisite information required for the agent to orchestrate a dependent tool call. The session object actually provides the data to the `suggest_outfit` and `create_fit_card`, and the parsed arguments from the LLM provide the data to the `search_listings` and `add_item_to_wardobe` tool calls. Session object attributes are updated between tool calls with the values returned by the tools.

For example:

```
# search_listings runs, returns a list of dicts, and the top result is stored
args = json.loads(tool_call.function.arguments)
results = search_listings(description=args["description"], size=args.get("size"),max_price=args.get("max_price"))
session["selected_item"] = results[0] 
tool_result = f"Found item: {results[0]}"

# next turn, the LLM triggers suggest_outfit, but the loop passes the session objects as args 
outfit_text = suggest_outfit(
    new_item=session["selected_item"],
    wardrobe=session["wardrobe"]
)
session["outfit_suggestion"] = outfit_text
tool_result = outfit_text

# create_fit_card runs using the data generated by the previous tool and passes session objects as args
caption = create_fit_card(
    outfit=session["outfit_suggestion"], 
    new_item=session["selected_item"]    
)
session["fit_card"] = caption
tool_result = caption
```

---

**End-to-end example workflow**
```
[User Input] "I mostly wear baggy jeans. Find me a vintage graphic tee under $30 and style it."
     │
     ▼
[Turn 1] 
 └── LLM detects implicit wardrobe context. 
 └── Triggers: add_items_to_wardrobe(items=[{"name": "baggy jeans"}])
 └── Result: Wardrobe array mutates. Tool logs summary text to message history.
     │
     ▼
[Turn 2]
 └── LLM detects search request and parses function arguments.
 └── Triggers: search_listings(**args)
 └── Result: Results list and top matching item stored in session dict. Item descriptors logged to message history.
     │
     ▼
[Turn 3]
 └── LLM sees search succeeded and notes styling prerequisite is met.
 └── Triggers: suggest_outfit(session["selected_item"])  <-- LLM does not parse any arguments.
 └── Result: Result string is stored to session and logged to message history.
     │
     ▼
[Turn 4]
 └── LLM sees search succeeded and notes fit card prerequisite is met.
 └── Triggers: create_fit_card(session["outfit_suggestion], session["selected_item"]) <-- LLM does not parse any arguments.
 └── Result: Result string is stored to session and logged to message history. There are no more tools to call.
 
[Turn 5]
 └── The LLM reviews the message history and sees that it has obtained all the required information, so makes no more tool call requests.
 └── The main loop catches the lack of remaining tool calls and returns the session object.
```

## Spec Reflection

**One way the spec helped you during implementation:**

**One way my implementation diverged from the spec, and why:**

For tool 4, `add_items_to_wardrobe`, I wrote in my spec that the function should just return a count of the added items if successful. Ultimately, this is pretty thin context for the orechestration LLM to use, and could potentially confuse the LLM and cause it to re-call the tool. I opted instead to return the items added and which category the items belong to.

## AI Usage

**Instance 1:**
- *What I gave the AI:*
The architecture section, planning loop logic, state management approach, system prompt, and structured tool definitions, and asked it to implement `run_agent`.

- *What it produced:*
It used `while True` for the main agent loop, meaning the only exit conditions for the loop were if `session["error"]` was set by a `search_listings` failure, or the agent determined no more tools needed to be called (success condition). The `while True` approach fails to catch the situation in which the agent keeps requesting tool calls, despite completing its work.

- *What I changed or overrode:*
I set a `MAX_TOOL_ROUNDS` variable to cap the agent loop to 10 rounds, update `while True` to a for loop that caps at `MAX_TOOL_ROUNDS`, and added an error message for if the agent is unable to complete its work within the round limit. `session["error"]` is set to the error message so it is displayed to the user in the Gradio display window.

**Instance 2:**
- *What I gave the AI:*
Tool definitions, tools.py implementation, and planning.md sections for the planning loop, state management approach, and error handling approach with the request that it write a system prompt that adhered to the design plan and specified constraints.

- *What it produced:*
It produced a system prompt that incorrectly stated that the LLM needed to pass the result of the `suggest_outfit` tool call to `create_fit_card`. This is incorrect per the documented state management strategy which states that it is session attributes that are passed as arguments to the `create_fit_card` tool by the main loop. This was further reinforced by the empty parameters secion of the tool definitions schema.

- *What I changed or overrode:*
I revised the system prompt tp make it clear where the LLM needs to pass tool results to tool calls and where it does not.