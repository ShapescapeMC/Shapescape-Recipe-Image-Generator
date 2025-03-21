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
import git.exc
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
            "\n"
            "The SHAPESCAPE_RIG_DATABASE_URL environment variable is not set. "
            "Please set the variable to the Git URL of a repository that "
            "contains the resources needed for the application to work."
            "\n\n"
            "For example you can set the variable to:\n"
            "- https://github.com/ShapescapeMC/Shapescape-Recipe-Image-Generator.git"
            "\n\n"
            "You can find more details in the documentation of the application."
            "\n"
        )
        exit(1)


@cache
def get_branch():
    try:
        return os.environ['SHAPESCAPE_RIG_BRANCH']
    except KeyError:
        logging.warning(
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

def _verify_repo_url(app_data_repo: git.Repo):
    '''
    Verifies if the repository is the correct one by checking the remote URL
    of the data repository in the cache agains the URL from the environment
    variable.

    :param app_data_repo: The repository object of the data repository of the
        application.
    '''
    url = get_database_url()
    if app_data_repo.remotes.origin.url != url:
        logging.error(
            "\n\n"
            "The URL from the SHAPECAPE_RIG_DATABASE_URL environment variable "
            "does not match the URL of the repository in the application data.\n"
            "Please remove the repository from the application data directory "
            "manually and try again.\n"
            f"Delete this directory: {get_app_data_path() / 'data'}"
            "\n\n"
            "More details:\n"
            f"- SHAPESCAPE_RIG_BRANCH variable: {url}\n"
            f"- Repository remote URL: {app_data_repo.remotes.origin.url}"
            "\n"
        )
        exit(1)

def _try_checkout_branch(repo: git.Repo):
    '''
    Tries to checkout the branch from the environment variable. If the branch
    does not exist, it stops the application with an error message.

    :param repo: The repository object of the data repository of the application.
    '''
    branch = get_branch()
    try:
        repo.git.checkout(branch)
    except git.exc.GitCommandError:
        logging.error(
            "\n\n"
            "The branch from your configuration (SHAPESCAPE_RIG_BRANCH or "
            "'main' by default) does not exist in the repository.\n"
            "Please check the branch name and try again.\n"
            "\n\n"
            "More details:\n"
            f"- Branch from your settings: {branch}\n"
            f"- Repository path: {get_app_data_path() / 'data'}"
            "\n"
        )
        exit(1)


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
        _try_checkout_branch(repo)
    else:
        logging.info(f"Updating the app data from: {get_database_url()}")
        repo = git.Repo(repo_path)
        _verify_repo_url(repo)
        _try_checkout_branch(repo)
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
    _verify_repo_url(repo)
    if repo.is_dirty(untracked_files=True):
        logging.info("There are uncommited changes in the database. Uploading to remote repository...")
        repo.git.add('-A')
        repo.git.commit('-m', 'Automatic update...')
    repo.git.push()
