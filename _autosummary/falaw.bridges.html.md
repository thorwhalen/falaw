# falaw.bridges

Bridges: derive auxiliary surfaces (skill, MCP, HTTP service) from the tool registry.

Each bridge is a thin adapter over `falaw.registry.list_tools()`. The point
is that adding a new surface (e.g. a CLI, a Slack bot, a TUI) is a new
bridge module — never a re-implementation of the operations themselves.

### Modules

| [`mcp`](falaw.bridges.mcp.html.md#module-falaw.bridges.mcp)         | MCP bridge: expose every falaw tool as an MCP tool.                     |
|---------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`service`](falaw.bridges.service.html.md#module-falaw.bridges.service) | HTTP service bridge (planned): expose falaw tools as a `qh` app.        |
| [`skill`](falaw.bridges.skill.html.md#module-falaw.bridges.skill)     | Render a Claude SKILL.md (and references) from the falaw tool registry. |
