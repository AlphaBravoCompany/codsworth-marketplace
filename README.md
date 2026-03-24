# Codsworth Marketplace

Plugin marketplace for [Codsworth](https://github.com/AlphaBravoCompany/codsworth) — build-verify-fix tools for Claude Code.

## Plugins

### Forge
Codebase-aware specification engine. Researches your code deeply, then conducts a grounded interview to produce foundry-ready specs.

### Foundry
Autonomous build-verify-fix loop with 4-stream verification:
- **TRACE** — LSP-powered wiring verification (Serena)
- **PROVE** — Spec-to-code requirement proof
- **SIGHT** — Browser-based UI audit (Playwright)
- **TEST** — Full test suite

Includes MCP server for phase gate enforcement and defect tracking.

**Forge plans. Foundry builds.**

## Install

```bash
# Add marketplace
claude plugin marketplace add AlphaBravoCompany/codsworth-marketplace

# Install plugins
claude plugin install forge@codsworth
claude plugin install foundry@codsworth

# Install MCP server (foundry state engine)
claude mcp add foundry -- uvx --from "git+https://github.com/AlphaBravoCompany/codsworth-marketplace#subdirectory=plugins/foundry/mcp-server" foundry-mcp --project-root .
```

## Update

```bash
claude plugin marketplace update codsworth
claude plugin update forge@codsworth
claude plugin update foundry@codsworth
```

## License

MIT
