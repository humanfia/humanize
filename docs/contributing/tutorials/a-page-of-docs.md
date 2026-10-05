# Add a page to these docs

In this tutorial you run this site locally, write a guide page, put it in the sidebar, prove
every link on it resolves, and look at it the way a reader will. It takes **twenty minutes**,
and every command is written out, in order.

::: info Before you start
Node and [pnpm](https://pnpm.io/). Nothing Python: the site builds without humanize
installed. `corepack enable` gives you the pnpm version `docs/package.json` pins.
:::

## Step 1: run the site

```sh
cd docs
pnpm install
pnpm dev        # http://localhost:5173/humanize/
```

Leave it running. It reloads on save, the sidebar included.

## Step 2: pick the section

A page answers one kind of question, and the question picks the section:

| The reader wants | Section |
| --- | --- |
| to understand how something works | [Features](/features/) |
| to do something with `hmz` | [User Guide](/user/) |
| to write a flow | [Weaver Guide](/weaver/) |
| to change humanize itself | [Contributing](/contributing/) |
| to look up a flag, key or signature | [Reference](/reference/) |

[Working on these docs](/contributing/docs#where-a-page-goes) says what a page in each looks
like.

## Step 3: write it

A page in a guide section is a guide page. Start from its skeleton, and drop the parts you have
nothing for:

````md
# My thing

In this guide you <what the reader will have done by the end>. Reach for it when <the
situation>.

::: info Before you start
- <what the reader needs already, with a link to where they get it>
:::

## How it works

<the idea, and its terms, as the example below needs them>

## Example: <what it does>

```sh
# the whole of it, never a fragment to finish
```

<what each part does, one numbered item per part>

<what it printed on a real run, and how to read that>

## Check it worked

## Pitfalls

## Next steps
````

Save it as `docs/user/my-thing.md`. As you write:

- Lead with doing. The first screen tells the reader what they will get.
- Run every example, and paste what it really printed.
- Link from the site root without the extension: `/user/afk`. Name assets in `public/` from
  the root: `/demo/run.png`. A terminal demo is `<HmzCast name="tui" alt="…" />`.
- Show something beyond prose: a code group, a table, a highlighted line, a demo.
- Wrap prose at 95 columns.

[The shape of a guide page](/contributing/docs#the-shape-of-a-guide-page) explains each part,
and [the writing rules](/contributing/docs#the-writing-rules) are the full list.

## Step 4: put it in the sidebar

A page that is not in `sidebar` does not appear. Open `.vitepress/config.mts`, find the sidebar
for the section's path, and add the entry to the group it belongs in:

```ts
'/user/': [
  { text: 'User Guide', link: '/user/' },
  // ...
  {
    text: 'At the prompt',
    collapsed: false,
    items: [
      // ...
      { text: 'My thing', link: '/user/my-thing' }, // [!code ++]
    ],
  },
],
```

`link` is the route, not the file: no `docs/`, no `.md`.

## Step 5: build it

```sh
pnpm build          # fails on a dead internal link
pnpm check:anchors  # fails on a dead #fragment
```

`pnpm build` fails on a link to a page that does not exist. It passes a link whose
`#fragment` is wrong, which is what `check:anchors` catches:

::: code-group

```text [A dead fragment]
user/my-thing.md: /user/efforts#kimis-swarm-mode -- no such heading -- did you mean #kimi-s-swarm-mode

1 dead fragment(s).
```

```text [All good]
every #fragment resolves
```

:::

Renaming a `##` heading moves its `#fragment`, and this finds every link that pointed at the
old one. To keep a fragment other pages link to while you rename the heading, give the heading
the old id: `## A new name {#the-old-name}`.

## Step 6: look at it

```sh
pnpm preview    # http://localhost:4173/humanize/
```

Open your page in light and dark, and at phone width. To screenshot all three,
[Look at it](/contributing/docs#look-at-it) has the Playwright command.

## Step 7: commit it

```sh
git add docs
git commit -m "docs(user): what my thing is and when to reach for it"
```

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/), with the section as
the scope. On a pull request into `main`, CI runs `pnpm build`, `pnpm check:anchors` and
`pnpm check:legible` again. A push to `main` deploys the site.

## Check it worked

- Your page is in the sidebar, under the group you chose, and the outline on the right lists
  its `##` headings.
- `pnpm build` and `pnpm check:anchors` both pass, the second ending `every #fragment
  resolves`.
- The screenshots show no raw markdown, no `:::`, and nothing wider than the screen at 390px.

## Next steps

- [Working on these docs](/contributing/docs) has the rest: the components, the terminal demos,
  and the screenshot check.
- [Your first patch](/contributing/tutorials/first-patch), for a change to the code the page
  describes.
