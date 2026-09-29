"""Thin, dependency-free bindings to the Linux facilities coganchor relies on.

Split by concern: :mod:`syscalls` (numbers and register layout),
:mod:`seccomp` (the trap and socket filters), :mod:`ptrace` (stop, inspect,
tamper), :mod:`procfs` (tracee memory, working directory, descriptor stealing)
and :mod:`landlock` (the paths and ports a process tree may reach).

Nothing is imported here: the tracing bindings pick a register map as they load
and refuse a host they have none for, and :mod:`landlock` has to be importable
on any host, a Mac included, to say that it is not available there.
"""
