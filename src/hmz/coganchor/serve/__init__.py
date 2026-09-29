"""The target half: carrying out on this machine what a client asks for.

Reached as ``hmz internal anchor``.  Nothing here may import from the agent half of
the package -- only :mod:`hmz.coganchor.proto` is shared -- because this is the
half that runs on the target, where there is no ptrace, no seccomp filter and
no guarantee of an x86-64 register map.

With one exception, the fence itself: :mod:`hmz.coganchor.fence`,
:mod:`hmz.coganchor.fence.abroad`, and the Landlock and socket-filter bindings
under :mod:`hmz.coganchor.linux` that ``hmz internal fence`` puts it up with.
Each imports nothing past the protocol and each other, each is imported only
where the handshake asks whether this machine can fence and where a command is
to be, and a target that cannot load them is one that cannot fence -- which it
says at the handshake, and which refuses a fenced command rather than running it
unfenced (:mod:`hmz.coganchor.serve.fencing`).
"""
