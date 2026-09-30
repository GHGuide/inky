"""The engine inside the desktop app. `inky-engine [args]` runs Inky; `inky-engine mcp-server` / `codex-mcp` run its MCP tools."""
import sys

if __name__ == "__main__":
    sub = sys.argv[1] if len(sys.argv) > 1 else ""
    if sub in ("mcp-server", "codex-mcp"):
        sys.argv.pop(1)
        if sub == "mcp-server":
            from inky.mcp_server import main
        else:
            from inky.codex_mcp import main
    else:
        from inky.__main__ import main
    main()
