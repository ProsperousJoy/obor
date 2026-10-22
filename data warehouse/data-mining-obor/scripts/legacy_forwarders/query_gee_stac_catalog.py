"""Compatibility forwarder for scripts.gee.query_stac_catalog"""
import runpy
if __name__ == "__main__":
    runpy.run_module("scripts.gee.query_stac_catalog", run_name="__main__")
