# FitFindr — Project 2

## Tool Inventory

**Error handling strategy**


## The Planning Loop

### State Management Approach

## End-to-end workflow


## Spec Reflection

**One way the spec helped you during implementation:**

**One way my implementation diverged from the spec, and why:**

For tool 4, `add_items_to_wardrobe`, I wrote in my spec that the function should just return a count of the added items if successful. Ultimately, this is pretty thin context for the orechestration LLM to use, and could potentially confuse the LLM and cause it to re-call the tool. I opted instead to return the items added and which category the items belong to.


## AI Usage

**Instance 1:**
- *What I gave the AI:*
The `suggest_outfit` tool stub and `planning.md` file and asked it to implement `suggest_outfit`.

- *What it produced:*
It produced a system prompt for the LLM that did specified the LLM's role, task, new item, and wardrobe items, but it was missing a specific instruction on the necessary length of the outfit suggestion. 

- *What I changed or overrode:*
I overrode the initial implementationa and asked Claude to incorporate a constraint for the outfit suggestion length.

**Instance 2:**
