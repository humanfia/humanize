---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# Many backends, one agent

<p class="hmz-tagline">Every role runs on the coding agent CLI you pick, under a login you already have.</p>

<HmzBackends />

<div class="hmz-facts">

- **Mostly no API key.** Each CLI runs as its own sign-in, or as an
  [account](/features/accounts) you add.
- **Models are asked once.** When you make an account, and kept. On a gateway, the gateway
  answers.
- **Auto sends nothing.** The model runs at its CLI's own default, on every backend.
- **Skills stay yours.** A flow's skills come and go with the session. pi, DeepSeek Harness,
  litellm and an ACP CLI take none.
- **Or no CLI at all.** `litellm` calls a model directly: one chat completion a turn over the
  session's history, no tools, no environment.
- **Three need an extra.** DeepSeek Harness, Kimi Code and litellm, at
  [install](/user/installation).

</div>

<div class="hmz-paths by-three">
  <a :href="withBase('/user/efforts')">
    <strong>Pick an effort</strong>
    <span>Every ladder, and when to reach for which rung.</span>
  </a>
  <a :href="withBase('/reference/providers')">
    <strong>Add a CLI</strong>
    <span>Every way into each backend, and adding one of your own.</span>
  </a>
  <a :href="withBase('/reference/agents')">
    <strong>What each one does</strong>
    <span>Every backend, exactly: models, efforts, skills, spend.</span>
  </a>
</div>
