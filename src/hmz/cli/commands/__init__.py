"""The commands of `hmz` that are written as :class:`hmz.cli.tree.Command`, a module a noun.

A module here holds `COMMANDS`, the commands it adds at the top of the tree -- usually one, a
group named for what it is about (`hmz chat`, `hmz runs`) with a command under it for each
thing done to it. :func:`hmz.cli.tree.commands` finds them by walking this package, so adding
a command is adding a module, and nothing else has to hear of it.
"""
