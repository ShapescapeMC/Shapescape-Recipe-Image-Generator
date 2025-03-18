'''
This is the main entry for the program. The main() function is a function that
is called when the user runs recipe-image-generator.exe file.
'''
from .gui import GuiProjectApp
from .cache import force_pull_database, CachedSettings
from .utils import is_connected
import logging


def main(
        skip_db_pull: bool=False,
        cached_settings: None | CachedSettings = None,
        save_cache_after_exit: bool = True):
    '''
    The main script of the recipe-image-generator.exe program.

    :param skip_db_pull: If True, the database will not be pulled from the
        internet. This is useful for debugging.
    :param cached_settings: If provided, overwrites the cached settings
        of the app with the provided settings.
    '''
    logging.basicConfig(
        format="%(asctime)s.%(msecs)03d %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        level=logging.INFO)
    if not skip_db_pull:
        if not is_connected():
            logging.warning(
                "You are not connected to the internet. "
                "The database will not be pulled.")
        else:
            force_pull_database()
    with GuiProjectApp(
            cached_settings=cached_settings,
            save_cache_after_exit=save_cache_after_exit) as app:
        app.mainloop()
