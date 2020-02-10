"""Smoke'n'mirrors utility library.

This package provides some common pattern to be reused in different interactive
installation projects.

Some core ideas

- Small python programs run independently and interacts via local UDP ports.
- Every sensor has its own Python script. Some common patterns (e.g. reading
  serial data from Arduino) are covered.
- A single script `integrate.py` reads data from all sensors on `signalin_port`,
  applies signal transformations and writes the output at a different frequency
  to `signals_port`.
- The script `animator.py` creates animation frames from the signals read from
  `signals_port` and sends both animation frames and signal stream via
  websockets to a javascript applicaiton.
- The javascript application shows the actual animation, the signal stream, and
  has controls to overwrite input signals, record/play, and interact otherwise
  with the installation.
"""
