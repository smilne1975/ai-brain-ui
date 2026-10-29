# levels report

A MicroStation key-in that lists the active model's levels and writes a CSV with pandas.

Run it from inside MicroStation with the key-in `MYREPORT LEVELS`. `levels.py` loads `levels.commands.xml` through `PythonKeyinManager.LoadCommandTableFromXml`.

`pandas` is not part of the Python that ships with MicroStation, so `MS_PYTHON` has to point at a separate install of the same version. `tools/levels.py` is a second copy of the same filename on purpose: Bentley drops key-ins when two loaded scripts share a name.
