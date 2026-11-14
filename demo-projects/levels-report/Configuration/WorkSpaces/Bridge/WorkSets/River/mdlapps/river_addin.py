"""River add-in loaded from MS_ADDINPATH."""

from MSPyBentley import ConfigurationManager


def load_river():
    root = ConfigurationManager.GetVariable("_USTN_WORKSETROOT")
    cell = ConfigurationManager.GetVariable("MS_CELL")
    return root, cell
