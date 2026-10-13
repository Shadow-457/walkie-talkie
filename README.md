<div align="center">
  <img src="logo.png" alt="Walkie-Talkie Logo" width="160">
  <h1>Walkie-Talkie</h1>
  <p><strong>Instant Agent-to-Agent Mesh Communication via Model Context Protocol (MCP)</strong></p>
  <p>
    <a href="https://github.com/Shadow-457/walkie-talkie/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-black.svg?style=flat-square" alt="License"></a>
    <a href="https://flet.dev"><img src="https://img.shields.io/badge/GUI-Flet%20(Python)-black.svg?style=flat-square" alt="GUI"></a>
    <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/protocol-MCP-2563eb.svg?style=flat-square" alt="MCP"></a>
  </p>
</div>

---

## ⚡ What is Walkie-Talkie?

Autonomous AI agents are brilliant alone &mdash; but complex engineering and research require **team coordination**. 

**Walkie-Talkie** is a desktop application (built with Python & Flet) that hosts an in-memory Model Context Protocol (MCP) server on your machine. When you plug multiple AI agents into your private Walkie-Talkie frequency, they can discover each other, pass context, report roadblocks, and share answers in real-time.

### The Big Difference: Zero Interruption
Traditional webhook listeners break an LLM's working loop. Walkie-Talkie injects pending peer messages **directly alongside active tool call responses** (like reading a file or running a test). Your agents stay completely in flow &mdash; zero context derailment, zero wasted tokens.

---

## ✨ Features

- **Instant Local MCP Server:** Launch the desktop app and copy your private frequency link (`http://localhost:8765/mcp`). No cloud accounts or API tokens required.
- **Mission Control GUI:** A snappy, minimalist Flet dashboard displays live connected agents, active routes, queue depth, and conversation logs.
- **Piggyback Message Injection:** Incoming peer messages slip cleanly into active execution turns without breaking agent focus.
- **Privacy & Security First:** All communications remain strictly local to your machine. Nothing is transmitted to external servers.
- **Cross-Platform:** Runs seamlessly on Linux, Windows, and macOS.

---

## 🚀 Quickstart

### Option 1: Run from Source

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Shadow-457/walkie-talkie.git
   cd walkie-talkie
   ```

2. **Install dependencies:**
   ```bash
   pip install flet mcp
   ```

3. **Launch Walkie-Talkie:**
   ```bash
   python main.py
   ```

---

## 🔌 Connecting Your Agents

### 1. Add MCP Server Config

Add Walkie-Talkie to your client's MCP configuration (Claude Desktop, Cursor, Cline, or custom agent):

```json
{
  "mcpServers": {
    "walkie-talkie": {
      "url": "http://localhost:8765/mcp",
      "transport": "sse"
    }
  }
}
```

### 2. Instruct Your Agent

Include this in your agent's system prompt:

```text
You have access to the Walkie-Talkie mesh network via MCP.
- Check active peer agents anytime using `wt_list_agents`.
- When you need assistance or updates from another agent, call `wt_send`.
- Pay attention to incoming peer messages delivered alongside your tool results.
```

---

## 🛠️ MCP Tools Reference

| Tool | Parameters | Description |
|---|---|---|
| `wt_send` | `to` (string), `message` (string), `priority` (optional) | Send a message to a specific agent ID or broadcast to `*`. |
| `wt_list_agents` | _None_ | Returns an array of all active connected agents and their status. |
| `wt_check_inbox` | `clear` (boolean, default: `true`) | Manually checks and dequeues pending peer messages. |

---

## 📄 License & Copyright

Copyright (C) 2026 **Hamza Shahbaz**

This project is free software: you can redistribute it and/or modify it under the terms of the **GNU General Public License v3.0**. See the [LICENSE](LICENSE) file for complete details.
