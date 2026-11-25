"""The views of the terminal interface, a module apiece.

A module here holds `VIEWS`, the :class:`hmz.tui.shell.View` it adds -- usually one. The shell
finds them by walking this package, binds the key each names, and opens each where it says:
the navigator on the left, the context on the right, or a page over the screen. Adding a view
is adding a module.
"""
