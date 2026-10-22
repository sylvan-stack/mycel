"""Installed-only fixture initialization, importable by spawned check workers.

The standard-library development release tool never imports this module. Its
installed check interpreter has the locked product and PostgreSQL dependencies.
"""
from pathlib import Path
from mycel._check_store import NativePostgresBackend


class InstalledFixtureBackend(NativePostgresBackend):
    """Seed low-level fixtures without inventing a user initialization audit.

    Explicit init/audit proofs supply their own uninitialized database and run
    the installed command. This existing distinction also applies in workers.
    """

    def initialize(self, settings_file):
        from urllib.parse import unquote, urlsplit
        from mycel._settings import load_settings
        from mycel._store import initialize_store
        snapshot = load_settings(path=settings_file)
        snapshot.require_valid()
        address = snapshot.values['store']['address']
        database = self._require_database(unquote(urlsplit(address).path[1:]), owned=True)
        if address != self.address(database):
            raise RuntimeError('automatic fixture initializer target differs')
        with self.connection(database) as connection:
            initialize_store(connection, dimensions=snapshot.values['embedding']['dimensions'])


def recover_owned(address, journal):
    """Use acknowledged records only, after all check processes have exited."""
    if address is None:
        return ()
    backend = NativePostgresBackend(address, _ownership_journal=Path(journal))
    return backend.recover_owned_databases()
