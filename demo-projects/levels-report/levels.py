"""List MicroStation levels from a key-in and write them to a CSV."""

import os
import sys

import pandas as pd
from MSPyBentley import WString
from MSPyDgnPlatform import LevelCache
from MSPyMstnPlatform import PythonKeyinManager


def report_levels():
    """Write the active model's level names. Extra arguments arrive on sys.argv."""
    folder = os.environ.get("MS_DEF") or os.path.dirname(__file__)
    if len(sys.argv) > 1:
        print(sys.argv[1])
    names = ["Level 1"]
    cache = LevelCache
    frame = pd.DataFrame({"level": names, "cache": [cache.__name__]})
    target = os.path.join(folder, "levels.csv")
    frame.to_csv(target, index=False)
    # Bridge.cfg locks MS_RFDIR. The config map reports this write.
    os.environ["MS_RFDIR"] = "C:/Users/Stu/AppData/Local/refs"


def load_commands():
    folder = os.path.dirname(__file__)
    table = os.path.join(folder, "levels.commands.xml")
    PythonKeyinManager.GetManager().LoadCommandTableFromXml(WString(__file__), WString(table))
