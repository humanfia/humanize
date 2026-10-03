# `/flow`: what is installed, then out to its first screen and into the flowverses -- the
# indexes more flows are installed from -- and into humanize's own to read what it lists.
#
# Nothing is fetched or installed here. The official index is the one `stage.py` wrote into
# this container; the fetch the interface tries as it opens fails quietly, and adding a
# flowverse is opened and walked back out of rather than answered.

Set Shell "bash"
Set FontSize 15
Set Width 1000
Set Height 560
Set Padding 12
Set Framerate 10
Set TypingSpeed 40ms

Hide
Type "cd /work/demo && clear" Enter
Type "hmz" Enter
Wait+Screen /ctrl\+c exit/
Show

Sleep 400ms

# What `/flow` opens on: every flow ready to run here, the ones built in first.
Type "/flow" Enter
Wait+Screen /Install more/
Sleep 1400ms

# Out a step, to the first screen: what is installed, and where more come from.
Left
Wait+Screen /indexes of flows/
Sleep 1200ms

# Into the flowverses: a card per index, how it stands and how much it lists.
Down
Enter
Wait+Screen /Add flowverse/
Sleep 1400ms

# Adding one is a repository and a name. Opened here, and walked back out of.
Tab
Sleep 400ms
Enter
Wait+Screen /Add a flowverse/
Sleep 1600ms
Escape
Wait+Screen /Indexes of flows to install/
Sleep 600ms

# Into `official`: each flow its index lists, at its newest release, ready to install.
Up
Sleep 300ms
Enter
Wait+Screen /lists, at their newest/
Sleep 1600ms
Screenshot "/out/flowverses.png"
Sleep 400ms
