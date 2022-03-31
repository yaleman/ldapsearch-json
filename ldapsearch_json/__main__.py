""" connects to the given LDAP server and dumps the results out """

from typer import run

from . import cli


def run_cli() -> None:
    """ for importing from pyproject"""
    run(cli)

if __name__ == "__main__":
    run(cli)
