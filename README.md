# NURU Library

Common code shared between different projects. To be linked as a git
submodule.

Setting up a new project:

- link `py/nurulib` into `PYTHONPATH`
- write a number of sensors
- use `nurulib.integrator.Integrator`
- use `nurulib.server.Server`
- create `launch.sh`
- do not forget about `tools/`
- ... refactor new functions from the project into this library ...

