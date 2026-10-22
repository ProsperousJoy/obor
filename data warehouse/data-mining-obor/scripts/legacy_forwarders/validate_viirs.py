"""Compatibility forwarder for scripts.viirs.validate_viirs"""
import runpy
if __name__ == "__main__":
    runpy.run_module("scripts.viirs.validate_viirs", run_name="__main__")
