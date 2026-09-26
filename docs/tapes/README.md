# The terminal demos

The GIFs and stills under `docs/public/demo/` are rendered from the `.tape` scripts here by
[VHS](https://github.com/charmbracelet/vhs), inside a container built by the `Dockerfile`
beside them. A tape may `Screenshot` a moment worth its own still as well as writing its GIF.

```sh
./render.sh                 # every tape
./render.sh tui.tape        # one of them
```

Needs `docker` and nothing else. The first run builds the image; after that a tape takes a few
seconds. The GIFs are **committed**; nothing in CI renders them.

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
Output "/out/my-demo.gif"

Set Shell "bash"
Set Width 1000
Set Height 560
Set Framerate 10
Set TypingSpeed 40ms

Hide
Type "cd /work/demo && clear" Enter
Show
```

Then render it and look at every frame before you commit it:

```sh
./render.sh my-demo.tape
docker run --rm -v "$PWD/../public/demo:/out" -v /tmp/frames:/frames \
    --entrypoint ffmpeg humanize-vhs \
    -i /out/my-demo.gif -vf 'select=not(mod(n\,20))' -vsync 0 /frames/my-demo_%02d.png
```

A demo shows humanize and nothing about the machine it was recorded on.

## The pieces

| | |
| --- | --- |
| `Dockerfile` | VHS, humanize built out of this checkout, and the stand-ins |
| `Dockerfile.dockerignore` | so the build context is a few files rather than the tree |
| `stage.py` | builds the throwaway world, at image build time |
| `standin/` | the coding agent CLIs that are not coding agent CLIs |
| `render.sh` | builds the image, runs the tapes, and fails on a GIF over 450 KB |
| `*.tape` | one demo each |

## Keeping them small

`check-added-large-files` refuses anything over 500 KB, and `render.sh` fails on anything over
450 KB. The clock is not bounded; the file is. What the current tapes are written against:

- `Set Width 1000`, `Set Height` between 500 and 620;
- `Set Framerate` between 10 and 20, the slower for a tape that is mostly a menu being read,
  and `Set TypingSpeed` between 25ms and 50ms;
- 8 to 20 seconds end to end.

A tape that has grown too large usually has too much `Sleep` in it.
