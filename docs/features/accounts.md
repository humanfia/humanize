---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# Two accounts of one CLI

<p class="hmz-tagline">Each agent runs as an account of its own. When one fails, the turn moves on.</p>

<HmzAccounts />

<div class="hmz-facts">

- **The CLI's own login.** Signing in runs it, and humanize keeps the result apart. Your own
  sign-in is never touched.
- **A subscription, a key or a gateway.** Two agents of one CLI can run as two of them at once.
- **One key, several CLIs.** An Anthropic key works in Claude Code, pi, Oh My Pi, opencode and
  mimocode. A subscription stays in its CLI.
- **Tried again first.** A turn that failed is retried at its place as often as you said.
- **Then the chain.** The next [place](/user/settings#fallback) takes over, and the one after it
  if that fails too: another account, CLI or model, in a new conversation.

</div>

<div class="hmz-paths by-three">
  <a :href="withBase('/user/settings#accounts')">
    <strong>Make an account</strong>
    <span>Signing one in, and pointing it at a key or a gateway.</span>
  </a>
  <a :href="withBase('/user/settings#fallback')">
    <strong>Set the chain</strong>
    <span>The waits, then the places to fall back to, in order.</span>
  </a>
  <a :href="withBase('/reference/providers')">
    <strong>Every way in</strong>
    <span>Each backend's accounts, every field, and adding a CLI.</span>
  </a>
</div>
