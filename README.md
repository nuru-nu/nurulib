# Smoke And Mirrors

Common code shared between different projects. To be linked as a git
submodule.

Setting up a new project:

- link `py/smanmi` into `PYTHONPATH`
- write a number of sensors
- use `smanmi.integrator.Integrator`
- use `smanmi.server.Server`
- create `launch.sh`
- do not forget about `tools/`
- ... refactor new functions from the project into this library ...

Example projects

- `git clone rizhom@figur.li:rizhom.git`
- `git clone mgcs@figur.li:rizhom.git`
