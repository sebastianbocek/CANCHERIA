"""Import anchors and self-tests for CANCHERIA frozen executables.

CANCHERIA intentionally keeps the historical WPSetter and configurator as
external Python source files so they remain editable/open-source beside the
Windows executables.  PyInstaller cannot statically inspect modules that are
later executed with :mod:`runpy`, so the frozen interpreter would otherwise
omit standard-library modules such as ``sqlite3`` and ``json``.

This module is imported by the launchers at build time.  Its explicit imports
make PyInstaller bundle the Python stdlib pieces required by the external
runtime scripts without pulling unrelated third-party packages from the
machine used to build the EXE.
"""
from __future__ import annotations

# Standard library used across WPSetter.py, calendario.py, the configurator,
# and the public cancheria package.  Keep these as normal imports: PyInstaller
# discovers them by walking this module.
import argparse  # noqa: F401
import ast  # noqa: F401
import asyncio  # noqa: F401
import base64  # noqa: F401
import calendar  # noqa: F401
import contextlib  # noqa: F401
import contextvars  # noqa: F401
import copy  # noqa: F401
import csv  # noqa: F401
import dataclasses  # noqa: F401
import datetime  # noqa: F401
import decimal  # noqa: F401
import difflib  # noqa: F401
import functools  # noqa: F401
import hashlib  # noqa: F401
import importlib  # noqa: F401
import importlib.util  # noqa: F401
import json  # noqa: F401
import logging  # noqa: F401
import os  # noqa: F401
import pathlib  # noqa: F401
import pickle  # noqa: F401
import pprint  # noqa: F401
import queue  # noqa: F401
import re  # noqa: F401
import runpy  # noqa: F401
import shutil  # noqa: F401
import signal  # noqa: F401
import smtplib  # noqa: F401
import sqlite3  # noqa: F401
import subprocess  # noqa: F401
import sys  # noqa: F401
import tempfile  # noqa: F401
import threading  # noqa: F401
import time  # noqa: F401
import traceback  # noqa: F401
import typing  # noqa: F401
import unicodedata  # noqa: F401
import uuid  # noqa: F401
import webbrowser  # noqa: F401
import zipfile  # noqa: F401
from email.mime.image import MIMEImage  # noqa: F401
from email.mime.multipart import MIMEMultipart  # noqa: F401
from email.mime.text import MIMEText  # noqa: F401
from zoneinfo import ZoneInfo  # noqa: F401

# Platform-specific file locking.  The Windows build needs msvcrt; POSIX source
# runs may use fcntl.  PyInstaller can safely see imports inside try blocks.
try:  # pragma: no cover - Windows only
    import msvcrt  # noqa: F401
except ImportError:  # pragma: no cover
    msvcrt = None  # type: ignore[assignment]

try:  # pragma: no cover - POSIX only
    import fcntl  # noqa: F401
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]


REQUIRED_STDLIB_MODULES = (
    "argparse",
    "ast",
    "asyncio",
    "base64",
    "calendar",
    "contextlib",
    "contextvars",
    "copy",
    "csv",
    "datetime",
    "decimal",
    "difflib",
    "email.mime.image",
    "email.mime.multipart",
    "email.mime.text",
    "hashlib",
    "importlib",
    "json",
    "logging",
    "pathlib",
    "pickle",
    "pprint",
    "re",
    "runpy",
    "shutil",
    "smtplib",
    "sqlite3",
    "subprocess",
    "tempfile",
    "threading",
    "time",
    "traceback",
    "typing",
    "unicodedata",
    "uuid",
    "webbrowser",
    "zipfile",
    "zoneinfo",
)


def stdlib_self_test() -> list[str]:
    """Return a list of import failures required by external runtime scripts."""
    failures: list[str] = []
    for module_name in REQUIRED_STDLIB_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - used by frozen build smoke-test
            failures.append(f"{module_name}: {type(exc).__name__}: {exc}")
    return failures
