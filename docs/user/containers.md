# Containers

Put a flow's work in a container when the agents need a toolchain or a filesystem you do not
have here. There are two ways to do it from the command line: run humanize itself inside the
container, or run an ssh server in the container and point one of the flow's environments at
it.

<div class="ct-ways">
  <div class="ct-way">
    <p class="ct-name">The whole run in a container</p>
    <p class="ct-type"><code>docker run … hmz exec …</code></p>
    <dl>
      <dt>agents run</dt><dd>in the container</dd>
      <dt>commands run</dt><dd>in the container</dd>
      <dt>the image needs</dt><dd>humanize, the agents' CLIs, and their sign-in</dd>
      <dt>works with</dt><dd>any flow</dd>
    </dl>
  </div>
  <div class="ct-way">
    <p class="ct-name">A container as an ssh host</p>
    <p class="ct-type"><code>hmz exec … -e ROLE=ssh@HOST/…</code></p>
    <dl>
      <dt>agents run</dt><dd>here, with your sign-in</dd>
      <dt>commands run</dt><dd>in the container</dd>
      <dt>the image needs</dt><dd>an ssh server, Python 3.12 or newer, and the project</dd>
      <dt>works with</dt><dd>a flow with a role for another machine</dd>
    </dl>
  </div>
</div>

## Try it: the whole run in one container

Mount the project at the path it already has, and run `hmz exec` in the image:

```sh
docker run --rm -it -v "$PWD:$PWD" -w "$PWD" my-image-with-hmz \
    hmz exec -f ralph_loop -a agent=claude/claude-opus-5:max \
    -b cost=20 "get the suite green"
```

Every agent and every command runs in the container. The project is your own directory,
mounted rather than copied, so the work is still there when the container goes. The price is
that the agents' CLIs run in there too, so the image has to have them installed and signed in.

## A container reached as an ssh host

A container running an ssh server is a host like any other. Name it in your ssh config, check
that `ssh test-box` works, and give it to a flow's environment role with `-e`:

::: code-group

```text [~/.ssh/config]
Host test-box
    HostName localhost
    Port 2222
    User me
```

```sh{3} [hmz exec]
hmz exec -f onbox \
    -a builder=claude/claude-opus-5:max -a reviewer=codex/gpt-5.6-sol:high \
    -e box=ssh@test-box/home/me/box/myproject \
    -b cost=20 "get the suite green"
```

:::

The agents stay on this machine, with their credentials and their link to the model provider,
so the container needs neither the CLIs nor a sign-in. What the builder reads, writes and runs
is in the container. This only works with a flow that has a role for another machine, like
`box` in `onbox`: [Remote execution](/user/remote-execution) has that flow, covers what `-e`
takes, and lists the pitfalls, which all apply here.

## A container of an agent's own

Code that builds agents by hand, outside a flow, can give an agent a container of an image you
name, brought up on its first turn and taken down with it. It needs Linux and `docker` on this
machine. That is Python below the flow API: see the [Machines reference](/reference/machines).

::: warning A container is not a permission boundary
An agent can still rewrite whatever is mounted into its container, your project included.
Narrowing what an agent may do is [permissions](/user/permissions). Read
[Security](/user/security).
:::

## See also

- [Remote execution](/user/remote-execution)
- [Machines reference](/reference/machines)
- [Permissions](/user/permissions)
- [Security](/user/security)

<style scoped>
.ct-ways {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin: 22px 0 8px;
}

.ct-way {
  padding: 14px 16px 10px;
  border: 1px solid var(--hmz-panel-border);
  border-radius: 14px;
  background: var(--hmz-panel-bg);
}

.ct-way p {
  margin: 0;
}

.ct-name {
  font-weight: 650;
  color: var(--vp-c-text-1);
}

.ct-type {
  margin-top: 6px !important;
  overflow-wrap: anywhere;
}

.ct-way dl {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 4px 12px;
  margin: 12px 0 4px;
  font-size: 14px;
  line-height: 1.5;
}

.ct-way dt {
  font-size: 12px;
  letter-spacing: 0.04em;
  color: var(--vp-c-text-3);
  padding-top: 1px;
}

.ct-way dd {
  margin: 0;
  color: var(--vp-c-text-2);
}

@media (max-width: 640px) {
  .ct-ways {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
