---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# Two accounts of one CLI

<p class="hmz-tagline">Each agent runs as an account of its own. When one fails, the conversation moves on.</p>

<HmzAccounts />

<div class="hmz-facts">

- **The CLI's own login.** Signing in runs it, and humanize keeps the result apart. Your own
  sign-in is never touched.
- **A subscription, a key or a gateway.** Two agents of one CLI can run as two of them at once.
- **One key, several CLIs.** An Anthropic key works in Claude Code, pi, opencode and mimocode. A
  subscription stays in its CLI.
- **Chains end.** One that loops stops the second time round. None falls back to this machine's
  own sign-in.
- **No account left?** The next [place](/user/settings#fallback) takes over: another CLI or
  model, in a new conversation.

</div>

<div class="hmz-paths by-three">
  <a :href="withBase('/user/settings#accounts')">
    <strong>Make an account</strong>
    <span>Signing one in, and pointing it at a key or a gateway.</span>
  </a>
  <a :href="withBase('/user/settings#fallback')">
    <strong>Set the chain</strong>
    <span>The accounts to fall back to, the next place, and the waits.</span>
  </a>
  <a :href="withBase('/reference/providers')">
    <strong>Every way in</strong>
    <span>Each backend's accounts, every field, and adding a CLI.</span>
  </a>
</div>
