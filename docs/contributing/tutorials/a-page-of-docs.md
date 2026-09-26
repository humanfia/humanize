# Add a page to these docs

**Twenty minutes.** You will run this site locally, write a page, put it in the sidebar, prove
every link on it resolves, and look at it the way a reader will.

::: tip Before you start
Node and [pnpm](https://pnpm.io/). Nothing Python: the site builds without humanize
installed. `corepack enable` gives you the pnpm version `docs/package.json` pins.
:::

## 1. Run the site

```sh
cd docs
pnpm install
pnpm dev        # http://localhost:5173/humanize/
```

Leave it running. It reloads on save, the sidebar included.

## 2. Pick the section

A page answers one kind of question, and the question picks the section:

| The reader wants | Section |
| --- | --- |
| to understand how something works | [Features](/features/) |
| to pick a flow to run | [Flows](/flows/) |
| to do something with `hmz` | [User Guide](/user/) |
| to write a flow | [Weaver Guide](/weaver/) |
| to change humanize itself | [Contributing](/contributing/) |
| to look up a flag, key or signature | [Reference](/reference/) |

[Working on these docs](/contributing/docs#where-a-page-goes) says what a page in each looks
like.

## 3. Write it

A User Guide page opens with what the thing is and a `## Try it`:

````md
# My thing

What it is and when you would reach for it, in two or three sentences.

## Try it

```sh
# the shortest thing that shows it working
```

## Then the rest of it
````

Save it as `docs/user/my-thing.md`. As you write:

- Lead with doing. The first screen gives the reader a result.
- Link from the site root without the extension: `/user/afk`. Name assets in `public/` from
  the root: `/demo/tui.gif`.
- Show something beyond prose: a code group, a table, a highlighted line, a demo.
- Wrap prose at 95 columns.

[The writing rules](/contributing/docs#the-writing-rules) are the full list.

## 4. Put it in the sidebar

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

## 5. Build it

```sh
pnpm build          # fails on a dead internal link
pnpm check:anchors  # fails on a dead #fragment
```

`pnpm build` fails on a link to a page that does not exist. It passes a link whose
`#fragment` is wrong, which is what `check:anchors` catches:

::: code-group

```text [A dead fragment]
user/my-thing.md: /user/tracing#whats-collected -- no such heading -- did you mean #what-s-collected

1 dead fragment(s).
```

```text [All good]
every #fragment resolves
```

:::

Renaming a `##` heading moves its `#fragment`, and this finds every link that pointed at the
old one.

## 6. Look at it

```sh
pnpm preview    # http://localhost:4173/humanize/
```

Open your page in light and dark, and at phone width. To screenshot all three,
[Look at it](/contributing/docs#look-at-it) has the Playwright command.

## 7. Commit it

```sh
git add docs
git commit -m "docs(user): what my thing is and when to reach for it"
```

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/), with the section as
the scope. On the pull request, CI runs `pnpm build` and `pnpm check:anchors` again. A push to
`main` deploys the site.

## What you have now

A page in the right section, in the sidebar, with every link and fragment on it checked.
[Working on these docs](/contributing/docs) has the rest: the components, the terminal demos,
and the screenshot check.
