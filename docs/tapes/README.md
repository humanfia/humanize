# The terminal demos

The demos in the docs are not pictures. Each one is the text a terminal was sent, with the
moment each piece of it came, kept as an [asciicast](https://docs.asciinema.org/manual/asciicast/v2/)
under `docs/public/demo/<name>.cast` and drawn by `<HmzCast>` in the reader's browser: the
words stay sharp at any zoom and can be selected, and a page fetches a few kilobytes of text
rather than a GIF.

The casts are recorded from the `.tape` scripts here. A tape is written in
[VHS](https://github.com/charmbracelet/vhs)'s language; `cast.py` plays it into `bash` on a
pseudo-terminal, inside a container built by the `Dockerfile` beside them, and writes down what
came back while the tape was showing.

```sh
./render.sh                 # every tape
./render.sh tui.tape        # one of them
```

Needs Apple's [`container`](https://github.com/apple/container) and nothing else
(`CONTAINER=docker ./render.sh` uses Docker instead). The first run builds the image; after that
a tape takes as long as it plays. The casts are **committed**; nothing in CI records them.

A page shows one with:

```md
<HmzCast name="tui" alt="what happens on it, for anyone who cannot watch" />
```

## A demo must not record anything private

That is why this is a container rather than a script you run on your own machine.

| | |
| --- | --- |
| the prompt | VHS's own `>`: no user, no host, no path |
| the workspace | `/work/demo`, built by `stage.py` |
| the homes | the container's own, under `/root` |
| the backends | `standin/claude` and `standin/codex`, which run nothing and exit 1 |
| the accounts | made by a way in that runs nothing, holding `not-a-real-token` or `not-a-real-key`; a gateway, if any, is at `gateway.example.invalid` |
| the runs, and the transcripts a collected trace is drawn out of | invented by `stage.py` |

**No tape takes a turn.** The interface demos open, show their own lists, and leave.

## A new tape

Copy the nearest existing tape and keep its opening:

```
Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 560
Set Padding 12
Set TypingSpeed 40ms

Hide
Type "cd /work/demo && clear" Enter
Show
```

`Width`, `Height`, `FontSize` and `Padding` give the terminal its columns and rows, as VHS would
fit them. Then record it and play it on its page, under `pnpm dev`, before you commit it. A demo
shows humanize and nothing about the machine it was recorded on.

`cast.py` understands what the tapes here use -- `Type`, the keys, `Ctrl+`, `Sleep`,
`Wait+Screen`, `Hide`, `Show` and `Set` -- and stops on anything else rather than guess.
What a `Hide` does goes on the recording as the screen it left behind, in one go, and a redraw
that leaves the screen as it was is left off it: a menu sends one twice a second.

## The pieces

| | |
| --- | --- |
| `Dockerfile` | humanize built out of this checkout, the stand-ins, and what `cast.py` needs |
| `cast.py` | plays a tape into a terminal and writes the cast |
| `stage.py` | builds the throwaway world, at image build time |
| `standin/` | the coding agent CLIs that are not coding agent CLIs |
| `render.sh` | builds the image, records the tapes, and fails on a cast over 450 KB |
| `*.tape` | one demo each |

The PNG stills beside the casts were taken by VHS at each tape's `Screenshot` lines, which
`cast.py` passes over. A still is retaken with VHS by hand, from the same tape.

## Keeping them short

8 to 20 seconds end to end. Idle stretches over 2 seconds are cut to 2 when a cast plays, but a
tape that runs long usually has too much `Sleep` in it.
