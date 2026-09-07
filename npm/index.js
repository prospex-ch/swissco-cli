#!/usr/bin/env node
"use strict";

// A launcher, not a second implementation. The server itself is the Python
// package `swissco-mcp` on PyPI; this hands stdio straight through to it so an
// npm-shaped host can start it the same way a Python-shaped one does.

const { spawn } = require("node:child_process");

const VERSION = require("./package.json").version;
const SPEC = `swissco-mcp@${VERSION}`;

const MISSING_UV = `swissco-mcp needs uv to run the Python server.

Install it:

  curl -LsSf https://astral.sh/uv/install.sh | sh     # macOS, Linux
  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"   # Windows

Or install the server directly and run it as swissco-mcp:

  pip install ${SPEC.replace("@", "==")}

https://swissco-mcp.readthedocs.io
`;

const child = spawn("uvx", [SPEC, ...process.argv.slice(2)], {
  stdio: "inherit",
});

child.on("error", (error) => {
  process.stderr.write(error.code === "ENOENT" ? MISSING_UV : `${error.message}\n`);
  process.exit(1);
});

// Forward the signals a host uses to stop a server, so the Python process gets
// the chance to shut its clients down rather than being orphaned.
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code === null ? 1 : code);
});
