# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Searches the listings data for items matching the description, size, and within the bounds set by the max price. Size and max price are both optional and default to None if not provided.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): Keywords describing what the user is looking for.
- `size` (str): A size string to filter listings by. None if not provided.
- `max_price` (float): The maximum price (inclusive) is looking to pay to filter listings by. None if not provided.

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->
The function returns a list of matching listing dicts based on the input parameters. The list is sorted from most relevant to least. 

**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->
If no listings match, the function will return an empty list. The agent should inform the user that it could not find relevant listings based on the provided description, size, or price (if they were provided), and suggest that the user try re-phrasing their description, and/or provide additional details.

---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
The function takes a an item the user is considering buying, the user's wardrobe, and suggests 1-2 complete outfits. 

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): A listing from the listings database representing an item the user wants to buy.
- `wardrobe` (dict): A dict with a key "items", which contains a list of wardrobe item dicts. May be empty.

**What it returns:**
<!-- Describe the return value -->
A non-empty string containing the outfit suggestions based on either the `new_item` and the `wardrobe`, or general styling based on `new_item` if no wardrobe is found.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->
If the wardrobe is empty or no outfit can be suggested, the agent should check the initial query to see if it included style preferences, and then offer styling advice based on that. If the initial query did not include any style preferences, then offer general styling advice based on `new_item`. The agent should also offer to add wardrobe pieces, providing the user with details on the information needed to fill out a wardrobe item (wardrobe-schema in human readable format).

---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Generates a 2-4 sentence outfit-of-the-day style caption for social media based on the suggested outfit and thrifted find.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (str): The outfit suggestions returned by `suggest_outfit` 
- `new_item` (dict): A listing from the listings database representing an item the user wants to buy.

**What it returns:**
<!-- Describe the return value -->
A 2-4 sentence string that can be used on TikTok/Instagram.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->
The agent should tell the user that the outfit data is incomplete, and then provide a caption based on the thrifted item only.

---

### Additional Tools (if any)

### Tool 4: add_items_to_wardrobe

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Adds one or more items to the user's session wardrobe.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `items_to_add` (list[dict]): A list of structured dict objects matching the wardrobe schema (name, category, colors, style_tags, notes).
- `wardrobe'` (list[dict]): The active session wardrobe list, passed by reference and modified in-place.

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->
A string containing a success message that includes number of pieces added. If there was an error and nothing could be added, a error string stating nothing was added is returned.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if no items were added? -->
It returns a string describing the failure: "Error: Could not save items to wardrobe state."

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->
The agent receives a list of messages containing the turn history, including the tools called and the tool-call results. The agent will make an initial call to the LLM to determine which tools need to be called depending on the user's query. The initial call includes the user's query, a system prompt, and tool definitions. While there are tools to call, the agent will extract the name of the tool and tool arguments (applicable to `search_listings` and `add_items_to_wardrobe` only), the tool will be executed, and the result saved in a variable. When no tool errors occur, session object attributes will be updated deterministically after tool results are returned to the main loop. Before moving to the next turn, the full assistant message will be appended to the messages list followed by the tool-call result. If a tool call sets a critical "error" attribute in the session object, the main loop catches this flag immediately after execution, breaks the loop, and exits early. When there are no more tools to call, the agent captures the LLM's final conversational message content, assigning it to the appropriate session attributes to handle soft fallbacks if necessary, completes the loop, and returns the session object.

---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->
State is managed through a hybrid approach: the conversational history (messages list) maintains the agent's logical memory, while the backend session dictionary handles the physical data transmission. While the actual content returned by the tools is used to update session attributes, tool results appended to the messages list are either context-rich summary strings or the literal text outputs of the tools. Context-rich summary strings are used for `search_listings` and `add_item_to_wardobe`, and the literal text outputs are used for `suggest_outfit` and `create_fit_card`. This allows the agent to track the tool execution history to determine if the tools have the pre-requisite information required for the agent to orchestrate a dependent tool call. The session object actually provides the data to the tool calls, and gets updated between tool calls depending on the values returned by calling the tools.

For example:

```
# search_listings runs, returns a list of dicts, and we store the top result
results = search_listings(description="Nike Hoodie", size="L")
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

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Inform the user they couldn't find any matching results and suggest providing greater detail and/or removing filter criteria. |
| suggest_outfit | Wardrobe is empty | Provide general styling advice based on the `selected_item`. |
| create_fit_card | Outfit input is missing or incomplete | Create a caption based on the `selected_item` descriptors alone. |
| add_items_to_wardrobe | No items added to wardrobe | Inform the user their items couldn't be added and provide general styling advice based on related descriptions provided. |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

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
    │       │     to inform user + provide text styling advice)       │
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

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

For `search_listings`, I'll give Claude the Tool 1 block from planning.md (inputs, return value, failure mode) and ask it to implement the function using `load_listings()` from the data loader. Before running it, I'll check that the generated code filters by all three parameters and handles the empty-results case. Then I'll test it with 3 queries.

I'll give Claude the implementation of `search_listings`, Tool 1 and Tool 2 blocks from planning.md (inputs, return value, failure mode), and `listings.json`, a system prompt for the tool's LLM call, parsing instructions for the item and wardrobe, and ask it to implement the function. Before running it, I'll check that the generated code injects the system prompt, invokes the chat completion endpoint, formats the wardrobe and selected items correctly, and handles error states. I'll test it by selecting 2 different items from the `listings.json` and 3 different items from `wardrobe_schema.json`.

For `create_fit_card`, I'll give Claude the Tool 3 block from planning.md (inputs, return value, failure mode), an example structured `selected_item` dict, a sample text output from `suggest_outfit`, a dedicated system prompt, and ask it to implement the function. Before running it, I'll check that the generated code cleanly injects the system prompt, invokes the chat completion endpoint, and successfully executes the fallback strategy of creating an engaging caption based on the selected_item descriptors alone if the outfit text input is missing or incomplete. Then I'll test it with 2 distinct valid outfit scenarios and 1 empty outfit string to verify the fallback logic triggers.

For `add_items_to_wardrobe`, I'll give Claude the Tool 4 block from planning.md (inputs, return value, failure mode) and an example structure of the user's active session wardrobe list, and ask it to implement the function. Before running it, I'll check that the generated code modifies the passed wardrobe list directly in-place by reference. I'll also ensure that it correctly handles the fallback check, returning the designated error string if the `items_to_add` payload is empty. Then I'll test it by passing a valid list of 2 items to ensure the main session data mutates properly, and an empty list to verify it returns the correct error text.

**Milestone 4 — Planning loop and state management:**

For `run_agent`, I'll give Claude the planning loop and architecture sections of `planning.md` along with all tool implementations, and ask it to implement the main orchestration loop. Before running it, I will verify that the loop uses the session object to pass live data between tools, deterministically updates session attributes using tool outputs, and catches critical search failures to break early. I'll check to ensure that the soft error fallbacks are handled and session state is updated right before returning the session object. I'll also make sure that session attributes (state) are updated using the returned values of from the tool calls, and that tool calls use session state attributes where relevant. Then I'll test the loop by running the agent against 3 specific query profiles to guarantee distinct execution flows: a full happy path (search + style + caption), a critical failure early exit (no listings found), and a single-intent query.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
<!-- What does the agent do first? Which tool is called? With what input? -->
The agent sends a prompt to the LLM that includes a system prompt, user query, and tool definitions. The LLM decides to call the `search_listings` tool, and uses the schema in the tool definition for the tool to parse the query and return a structured JSON object with the required agruments: description, size, max price. The code in the main loop for the `search_listing` tool call executes the function using the response's tool call arguments as input. 

**Step 2:**
<!-- What happens next? What was returned from step 1? What tool is called now? -->
`search_listings` returns a sorted list of relevant items. This list is then saved to `session["search_results"]`, and the top of the list is saved to `session["selected_item"]`. The code in this section sets the tool result to a formated string description of the found item. The agent prompts the LLM again, but now the message history includes the tool execution and tool result message. The LLM uses this history to determine the next tool call: `suggest_outfit`.

**Step 3:**
<!-- Continue until the full interaction is complete -->
`suggest_outfit` requires no arguments from the LLM response and instead uses the session state. The code in the main loop for `suggest_outfit` calls the function with the arguments from the session state: `session["selected_item"]` and `session["wardobe"]`. 

**Step 4:**
<!-- Continue until the full interaction is complete -->
`suggest_outfit` returns a string, which gets stored in `session["outfit_suggestion"]`. The tool result is also set to the returned string. The agent prompts the LLM again, but now the message history includes the tool execution and tool result message. The LLM uses this history to determine the next tool call: `build_fit_card`.

**Step 5:**
<!-- Continue until the full interaction is complete -->
`build_fit_card` returns a string, which gets stored in `session["fit_card"]`. The tool result is also set to the returned string. The agent prompts the LLM again, but now the message history includes the tool execution and tool result message. The LLM uses this history to determine that no more tools need to be called, so the agent ends the loop and returns the session.

**Final output to user:**
<!-- What does the user actually see at the end? -->
`handle_query` in `app.py` takes the session object and formats the data stored in `session["selected_item"]`, which it then displays in the "Top Listing Found" window. The outfit suggestion string is displayed directly from `session["outfit_suggestion"]` in the "Outfit idea" window. Finally, the fit card caption is displayed directly from `session["fit_card"]` in the "Your Fit Card" window.
