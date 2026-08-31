"""
Quick start: Using FreeCode MCP with Claude
============================================

This example shows how to set up and use FreeCode's MCP server with Claude Desktop.

Step 1: Install FreeCode (if not already installed)
====================================================

git clone https://github.com/A56-A5/freecode.git
cd freecode
pip install -e .


Step 2: Configure Claude Desktop
==================================

1. Find your claude_desktop_config.json:
   - macOS/Linux: ~/.claude/claude_desktop_config.json
   - Windows: %APPDATA%\Claude\claude_desktop_config.json

2. Add freecode MCP server configuration:

{
  "mcpServers": {
    "freecode": {
      "command": "freecode",
      "args": ["mcp", "/path/to/your/project"],
      "disabled": false
    }
  }
}

   Replace /path/to/your/project with your actual project directory, e.g.:
   - macOS/Linux: /home/user/projects/my-app
   - Windows: C:\\Users\\user\\projects\\my-app

3. Restart Claude Desktop

4. FreeCode tools should now appear in Claude's context menu!


Step 3: Use FreeCode Tools in Claude
=====================================

Try any of these prompts:

1. "Read the main.py file and explain what it does"
   → Claude uses read_file tool

2. "Search for all TODO comments in the codebase"
   → Claude uses grep_search tool

3. "What's the git status and recent commits?"
   → Claude uses git_status and git_log tools

4. "Fix the bug in auth.py and run the tests"
   → Claude uses read_file, write_file, and run_command tools

5. "Show me the difference between this branch and main"
   → Claude uses git_diff tool


Example: Claude fixing a bug
=============================

You: "There's a bug in the authentication module. Can you find and fix it?"

Claude can now:
1. search the codebase for auth-related files
   → grep_search("auth", "*.py")

2. read the suspicious file
   → read_file("src/auth.py")

3. check git history for recent changes
   → git_log(n=20)

4. examine the diff
   → git_diff()

5. write a fix
   → write_file("src/auth.py", fixed_content)

6. run tests to verify
   → run_command("pytest tests/")

All without hitting any API rate limits!


Troubleshooting
===============

"Claude doesn't see FreeCode tools"
- Restart Claude Desktop after updating config
- Check that the config file is valid JSON
- Verify the path to your project is correct
- Try: echo $HOME to get the correct home directory path

"Permission denied when running commands"
- Make sure you have permission to execute files
- Try running a simple command first: freecode mcp .

"MCP server crashes or disconnects"
- Check error logs: cat ~/.freecode/mcp-server.log
- Try running manually to see errors: freecode mcp /path/to/project
- Make sure project directory exists and is readable


Advanced: Multiple Projects
============================

You can set up multiple MCP servers for different projects:

{
  "mcpServers": {
    "freecode-project1": {
      "command": "freecode",
      "args": ["mcp", "/home/user/projects/project1"]
    },
    "freecode-project2": {
      "command": "freecode",
      "args": ["home/user/projects/project2"]
    }
  }
}


Tips & Tricks
=============

1. Use @freecode in Claude to explicitly reference tools:
   "@freecode read the package.json file"

2. Ask for approval before dangerous operations:
   "Show me what changes you'd make before applying them"

3. Combine with other tools:
   "Use freecode to read the config, then help me understand it"

4. Search before making changes:
   "@freecode search for all imports of this module"

5. Check git before committing:
   "@freecode show the git status and diff"


Next Steps
==========

1. Read docs/MCP.md for full reference
2. Check individual tool documentation
3. Explore FreeCode's features: https://github.com/A56-A5/freecode
4. Try the main TUI: freecode


Questions?
==========

- GitHub Issues: https://github.com/A56-A5/freecode/issues
- Documentation: ./docs/MCP.md
- Main README: ./README.md
"""

# This file is for documentation — not executable Python code
# You can read it as plain text or render it as markdown
