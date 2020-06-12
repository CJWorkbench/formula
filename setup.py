#!/usr/bin/env python

from setuptools import setup

setup(
    name="formula",
    version="0.0.1",
    description="Run Excel or Python formula between columns and store result in a new column",
    author="Adam Hooper",
    author_email="adam@adamhooper.com",
    url="https://github.com/CJWorkbench/formula",
    packages=[""],
    py_modules=["formula"],
    install_requires=["pandas~=0.25.0", "formulas~=1.0.0", "cjwmodule>=1.4.0"],
)
