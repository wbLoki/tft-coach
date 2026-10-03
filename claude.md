## Framework

This is an **OW-Electron** project (`overwolf/`). Use `docs-ow-electron-current` for all Overwolf docs MCP queries.

## API lookup order

When any question involves an Overwolf API, method, type, or interface:

1. **Search local Overwolf `.d.ts` files first**—glob `overwolf/node_modules/@overwolf/**/*.d.ts` and grep for the symbol.
 These are the ground truth for what is actually installed and available in this project.

2. **Query the Overwolf docs MCP** when:
 - The symbol isn't found in the local type definitions
 - The user needs conceptual explanation, guides, or code examples beyond what types convey

## Overwolf docs MCP server

Available tool: `mcp__ow-docs-mcp__algolia_search_index_overwolf`

Always use `facet_docusaurus_tag: docs-ow-electron-current` for all queries.

If the MCP server is not connected (not listed in available MCP servers), tell the user and ask them to reload Claude Code. Do NOT fall back to curl, web search, or any other method.

## General guidelines

- All Overwolf packages live under the `@overwolf` npm scope—this is always the right place to start when exploring what APIs are available.
- Avoid guessing API shapes. If a type isn't in the local `.d.ts` files and the MCP has no result, say so rather than inferring.
- When referencing a type or method found locally, include the file path and line number so the user can navigate to it directly.