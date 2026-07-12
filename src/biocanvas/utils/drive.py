# biocanvas/utils/drive.py
"""Placeholder for the SharePoint drive client.

``MSDrive`` previously came from the external ``bifrost`` monorepo
(``bifrost.auth.drive``), which is no longer available now that biocanvas has
been extracted into its own repository. This stub preserves the interface
:class:`~biocanvas.utils.io.SharePoint` depends on so imports keep resolving.

A real implementation backed by a local SQLite database is planned as a
follow-up (see temp_instructions.md); until then every method raises
NotImplementedError.
"""
from typing import Any, Dict, List


class MSDrive:
    """Placeholder client matching the interface consumed by SharePoint.

    Methods mirror the four calls :class:`~biocanvas.utils.io.SharePoint`
    makes: ``search_for_site``, ``list_site_drives``, ``list_items``, and
    ``data_content``. All raise ``NotImplementedError`` until a real backend
    is wired in.
    """

    def search_for_site(self, project_name: str) -> Dict[str, List[Dict[str, Any]]]:
        raise NotImplementedError(
            "MSDrive is a placeholder; a local database backend has not been wired in yet."
        )

    def list_site_drives(self, site_id: str) -> Dict[str, List[Dict[str, Any]]]:
        raise NotImplementedError(
            "MSDrive is a placeholder; a local database backend has not been wired in yet."
        )

    def list_items(self, drive_id: str, folder_path: str) -> Dict[str, List[Dict[str, Any]]]:
        raise NotImplementedError(
            "MSDrive is a placeholder; a local database backend has not been wired in yet."
        )

    def data_content(self, drive_id: str, item_path: str) -> bytes:
        raise NotImplementedError(
            "MSDrive is a placeholder; a local database backend has not been wired in yet."
        )
