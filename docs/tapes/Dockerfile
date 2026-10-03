# The world the demos are recorded in: humanize built out of this checkout, a stand-in for the
# coding agent CLIs, and `cast.py` to play a tape into a terminal.
#
# Nothing in here signs in to anything, and nothing in here is yours: the demos run in this
# container's own scratch home, in a throwaway project, so a recording cannot pick up an
# account, a path or a hostname. See README.md beside this file.
#
# Built and run by ./render.sh, which hands it a context of only the files named below.

FROM python:3.13-slim

RUN pip install --no-cache-dir uv

# What `cast.py` drives a terminal with, kept apart from humanize's own environment.
RUN uv venv /opt/cast \
    && uv pip install --python /opt/cast/bin/python pexpect pyte \
    && rm -rf /root/.cache

# humanize out of this checkout rather than out of a release, so a demo is of the code beside
# it. Only what the build backend reads, so editing a tape does not rebuild the environment.
COPY pyproject.toml README.md LICENSE /src/
COPY src /src/src
RUN uv venv /opt/hmz \
    && uv pip install --python /opt/hmz/bin/python /src \
    && rm -rf /root/.cache

COPY standin /opt/standin
COPY stage.py /opt/stage.py

ENV PATH=/opt/hmz/bin:/opt/standin:$PATH \
    HUMANIZE_HOME=/root/.hmz \
    CLAUDE_CONFIG_DIR=/root/.claude \
    CODEX_HOME=/root/.codex \
    TERM=xterm-256color

# Staged at build time so a tape spends its time on humanize rather than on `mkdir`.
RUN /opt/hmz/bin/python /opt/stage.py
