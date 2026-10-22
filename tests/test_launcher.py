"""Tests for the launcher (main.py): choosing a UI with --ui.

Nothing here imports a UI module in-process - other tests assert tkinter is
never loaded headlessly - so UI modules are inspected by source or in a
subprocess.
"""
import ast
import importlib.util
import os
import subprocess
import sys

import pytest

from conftest import ROOT
import main


def test_default_ui_is_tkinter():
    assert main.DEFAULT_UI == "tkinter"
    assert main.parse_args([]).ui == "tkinter"


def test_tkinter_can_be_chosen_explicitly():
    assert main.parse_args(["--ui", "tkinter"]).ui == "tkinter"


def test_unknown_ui_is_rejected(capsys):
    with pytest.raises(SystemExit):
        main.parse_args(["--ui", "nope"])
    assert "invalid choice" in capsys.readouterr().err


def test_dearpygui_can_be_chosen():
    assert main.parse_args(["--ui", "dearpygui"]).ui == "dearpygui"


@pytest.mark.parametrize("name", sorted(main.UIS))
def test_every_registered_ui_has_a_run_function(name):
    path = importlib.util.find_spec(main.UIS[name]).origin   # a module, or a package's __init__
    tree = ast.parse(open(path, encoding="utf-8").read())
    runs = [node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "run"]
    assert runs, f"{main.UIS[name]}.py must define run(api)"
    assert [arg.arg for arg in runs[0].args.args] == ["api"]


def test_launcher_does_not_import_tkinter():
    code = (
        "import sys; import main; "
        "assert 'tkinter' not in sys.modules, 'main.py pulled in tkinter'; "
        "print('clean')"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "clean" in out.stdout


def test_only_the_tkinter_ui_includes_the_database_editor():
    """The editor stays separate: no UI but tkinter may load it."""
    for name, module in main.UIS.items():
        if name == "tkinter":
            continue
        # Import the UI and, for a package, every module in it
        code = (
            "import importlib, pkgutil, sys; "
            f"ui = importlib.import_module('{module}'); "
            "[importlib.import_module(m.name) for m in "
            "pkgutil.walk_packages(getattr(ui, '__path__', []), ui.__name__ + '.')]; "
            "assert 'database_editor' not in sys.modules, "
            f"'{module} pulls in the database editor'; print('clean')"
        )
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                             capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        assert "clean" in out.stdout
