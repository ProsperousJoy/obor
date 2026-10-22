"""Compatibility forwarder for scripts.bmkg.explore_bmkg"""
import runpy
if __name__ == "__main__":
    runpy.run_module("scripts.bmkg.explore_bmkg", run_name="__main__")
