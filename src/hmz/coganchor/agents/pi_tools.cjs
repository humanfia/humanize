// A flow's own callbacks, as tools of pi's: the extension `hmz.coganchor.agents.pi` hands pi
// with `--extension` wherever a flow offers its agent anything.
//
// pi takes no MCP server on its command line -- its own MCP support reads `mcp.json` out of
// pi's home, which is the user's and not a flow's to write -- but it does take an extension,
// and an extension may register a tool. So this one starts the bridge every backend is
// handed (`hmz internal tools`), asks it what is offered, and registers each tool as
// `humanize_<name>` -- pi's own tools are called what a flow's may be, and a `write` of the
// flow's would otherwise be pi's, or one `--exclude-tools` withholds; a call of one is a
// `tools/call` through the bridge under the name the flow gave it, which is the callback
// running in the flow's own process.
//
// The bridge's argv is in `HMZ_PI_TOOLS`, as JSON. Where it is not set this registers
// nothing, so a pi that finds this file without Humanize behind it is the pi it was.
//
// CommonJS so that it needs nothing from pi to load: pi's loader takes a module whose export
// is the factory, and waits for one that is asynchronous, which is what lets the tools be
// listed before the first turn is taken.
"use strict";

const { spawn } = require("node:child_process");
const readline = require("node:readline");

module.exports = async function humanizeTools(pi) {
  const argv = JSON.parse(process.env.HMZ_PI_TOOLS || "null");
  if (!Array.isArray(argv) || argv.length === 0) return;
  const bridge = spawn(argv[0], argv.slice(1), { stdio: ["pipe", "pipe", "inherit"] });
  const waiting = new Map();
  let asked = 0;
  // Held up only while a call is waiting on it: pi ends when it is done, and an idle bridge
  // is never what keeps it up.
  const holding = () => {
    if (waiting.size > 0) bridge.stdout.ref();
    else bridge.stdout.unref();
  };
  bridge.unref();
  bridge.stdin.unref();
  holding();
  // Once the bridge is gone every call fails at once, the waiting ones and every one after.
  let dead = null;
  const gone = (why) => {
    dead ??= why;
    for (const { reject } of waiting.values()) reject(dead);
    waiting.clear();
    holding();
  };
  bridge.on("error", gone);
  bridge.stdin.on("error", gone);
  bridge.on("exit", () => gone(new Error("the Humanize tool bridge exited")));
  readline.createInterface({ input: bridge.stdout }).on("line", (line) => {
    let said;
    try {
      said = JSON.parse(line);
    } catch {
      return;
    }
    const held = waiting.get(said.id);
    if (held === undefined) return;
    waiting.delete(said.id);
    holding();
    if (said.error) held.reject(new Error(said.error.message));
    else held.resolve(said.result);
  });
  const ask = (method, params) =>
    new Promise((resolve, reject) => {
      if (dead !== null) return reject(dead);
      asked += 1;
      waiting.set(asked, { resolve, reject });
      holding();
      bridge.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id: asked, method, params })}\n`);
    });

  let tools;
  try {
    await ask("initialize", {
      protocolVersion: "2025-06-18",
      capabilities: {},
      clientInfo: { name: "pi", version: "0" },
    });
    ({ tools } = await ask("tools/list", {}));
  } catch (why) {
    // pi carries on past an extension that failed to load, which here would be a turn with
    // none of what the flow offered in front of the model: so pi is ended instead, and the
    // turn fails saying why.
    process.stderr.write(`Humanize: the flow's tools could not be reached: ${why.message}\n`);
    process.exit(1);
  }
  for (const tool of tools) {
    pi.registerTool({
      name: `humanize_${tool.name}`,
      label: tool.name,
      description: tool.description,
      parameters: tool.inputSchema,
      async execute(_toolCallId, params) {
        const result = await ask("tools/call", { name: tool.name, arguments: params ?? {} });
        // Thrown rather than returned, which is how pi is told a tool failed.
        if (result.isError) throw new Error(result.content.map((one) => one.text).join("\n"));
        return { content: result.content, details: undefined };
      },
    });
  }
};
