'''
This module handles the cache. The cache is a directory stored on the user file
in %userprofile%/AppData/Local/Shapescape.

Cache includes most recent user application settings and the data from the
ShapescapeMC/recipe-image-generator-data repository. This repository includes
some resource packs and mappings of items to their textures.
'''
from __future__ import annotations
from functools import cache
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import json
import git
import logging

import appdirs

from better_json_tools import load_jsonc
from .utils import is_connected

import os

# DATABASE_URL = "https://github.com/ShapescapeMC/recipe-image-generator-data.git"
# BRANCH = "master"

@cache
def get_database_url() -> str:
    try:
        return os.environ['SHAPESCAPE_RIG_DATABASE_URL']
    except KeyError:
        logging.error(
            "SHAPESCAPE_RIG_DATABASE_URL environment variable is not set.\n"
            "This is required for the program to work. The variable should "
            "store the URL to a Git repository, with the mapping and textures "
            "for the program to work, for example:\n"
            "'https://github.com/ShapescapeMC/recipe-image-generator-data.git'\n"
            "Your Git should be authorized to access and modify the repository."
        )
        exit(1)


@cache
def get_branch():
    try:
        return os.environ['SHAPESCAPE_RIG_BRANCH']
    except KeyError:
        print(
            "SHAPESCAPE_RIG_BRANCH environment variable is not set. "
            "Using 'main' as default.")
    return "main"

@cache
def get_app_data_path():
    '''Returns the path to the application data directory.'''
    return Path(appdirs.user_data_dir('recipe-image-generator', 'Shapescape'))

@dataclass
class CachedSettings:
    '''Data class that stores cached settings of the app for GUI fields.'''
    resource_pack_path: Optional[Path] = None
    behavior_pack_path: Optional[Path] = None
    local_data_path: Optional[Path] = None
    image_scale: int = 1

    def __post_init__(self):
        if self.resource_pack_path is not None:
            self.resource_pack_path = Path(self.resource_pack_path)
        if self.behavior_pack_path is not None:
            self.behavior_pack_path = Path(self.behavior_pack_path)
        if self.local_data_path is not None:
            self.local_data_path = Path(self.local_data_path)

    @staticmethod
    def from_settings_file() -> CachedSettings:
        '''
        Tries to load the settings.json from cache to be used in the GUI.
        '''
        try:
            settings_path = get_app_data_path() / "cache/settings.json"
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            return CachedSettings(**load_jsonc(settings_path).data)
        except (FileNotFoundError, json.decoder.JSONDecodeError):
            return CachedSettings()

    def as_dict(self):
        return dict(
            resource_pack_path=self.resource_pack_path.resolve().as_posix(),
            behavior_pack_path=self.behavior_pack_path.resolve().as_posix(),
            local_data_path=self.local_data_path.resolve().as_posix(),
            image_scale=self.image_scale
        )

    def save(self):
        '''
        Saves the GUI settings provided by the user to application data. So they
        can be used in the GUI next time the app is launched.

        :param settings: The object that represents the settings.
        '''
        out_path = (get_app_data_path() / "cache/settings.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open('w') as f:
            json.dump(self.as_dict(), f, indent='\t', sort_keys=True)

# Database synchronisation
def force_pull_database():
    '''
    Clones or pulls the database repository.
    '''
    repo_path = get_app_data_path() / "data"
    logging.info(f"The database path is: {repo_path.as_posix()}")
    if not repo_path.exists():
        repo_path.mkdir(parents=True, exist_ok=True)
        logging.info(f"Downloading the app data from: {get_database_url()}")
        repo = git.Repo.clone_from(get_database_url(), get_app_data_path() / "data")
        repo.git.checkout(get_branch())
    else:
        logging.info(f"Updating the app data from: {get_database_url()}")
        repo = git.Repo(repo_path)
        repo.git.checkout(get_branch())
        repo.git.reset(f'origin/{get_branch()}')
        repo.git.reset('--hard')
        repo.git.clean('-fd')
        repo.remotes.origin.pull()

def push_database():
    '''
    Commits local changes to the database repository and pushes them.
    '''
    if not is_connected():
        logging.warning(
            "Not connected to the internet. Skipping database upload...")
        return
    repo_path = get_app_data_path() / "data"
    logging.info(f"The database path is: {repo_path.as_posix()}")
    repo = git.Repo(repo_path)
    if repo.is_dirty(untracked_files=True):
        logging.info("There are uncommited changes in the database. Uploading to remote repository...")
        repo.git.add('-A')
        repo.git.commit('-m', 'Automatic update...')
    repo.git.push()
