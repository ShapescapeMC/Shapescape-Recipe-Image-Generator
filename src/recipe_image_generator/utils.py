'''
Various utilities for accessing data from packs and performing "other"
functions that didn't match any other category.
'''
# Everything in this script is cached in global variables. It's not a nice
# solution but it's fast. This should be fixed in the future.
import logging
from typing import Iterable, Dict, Callable, List, Tuple
from pathlib import Path
import json
import re
from itertools import chain

from PIL import Image, ImageChops

from better_json_tools import load_jsonc
from textwrap import wrap
import io
import socket

def better_wrap(text: str, width: int):
    '''
    A wrapping function for text that respects new line charcters and
    doesn't count them for wrapping.

    :param text: text to wrap
    :param width: max width of a line
    '''
    lines = text.splitlines()
    output_lines: list[str] = []
    for line in lines:
        output_lines.extend(
            wrap(line, width=width, replace_whitespace=False, break_on_hyphens=False))
    return "\n".join(output_lines)


def is_connected(hostname: str = "1.1.1.1"):
    '''
    Checks if the computer is connected to the internet.
    '''
    try:
        host = socket.gethostbyname(hostname)
        s = socket.create_connection((host, 80), 2)
        s.close()
        return True
    except Exception:
        pass  # we ignore any errors, returning False
    return False

class TextureNotFound(Exception):
    '''Exception raised when the texture is not found'''

# Load the shared data files.
TextureMap = Dict[str, Dict[str, str]]

ColorTuple = Tuple[int, int, int, int]

def find_existing_subpath(roots: Iterable[Path], subpath: str):
    serched_subpaths = []
    for root in roots:
        curr_subpath = root / subpath
        serched_subpaths.append(curr_subpath.as_posix())
        if curr_subpath.exists():
            return curr_subpath
    raise FileNotFoundError(
        "Unable to locate the file. Seared paths:\n"
        "".join(f"\t- {s}\n" for s in serched_subpaths))

# Data sources
def texture_map_from_rp(rp_path: Path) -> TextureMap:
    '''
    Creates texture map based on "item_texture.json" file in the resource pack.

    :param resource_pack_path: path to the resource pack.
    :return: texture map object.
    '''
    result: TextureMap = {}
    path = rp_path / "textures/item_texture.json"
    texture_data = load_jsonc(path).data["texture_data"]
    if not isinstance(texture_data, dict):
        raise TextureNotFound(
            f"Texture data in {rp_path.as_posix()} is not a"
            " dictionary.")
    for k, v in texture_data.items():
        textures = v["textures"]
        if isinstance(textures, str):
            result[k] = {"0": f"RP/{textures}"}
        elif isinstance(textures, list):
            result[k] = {str(i):f"RP/{t}" for i, t in enumerate(textures)}
        else:
            logging.warning(
                f"Texture '{k}' in {path.as_posix()} is not a string "
                "or a list of strings. Skipped.")
    return result

def texture_map_from_hardcoded(path: Path) -> TextureMap:
    '''
    Loads texture map from the hardcoded "data_map.json" file.

    :param path: path to the file.
    :return: texture map object.
    '''
    return load_jsonc(path).data

def lang_file(lang_file_path: Path) -> Dict[str, str]:
    '''
    Loads data from a .lang file into a dictionary of translations.

    :param lang_file_path: path to the .lang file.
    '''
    with lang_file_path.open('r', encoding="utf8") as f:
        translation_list = f.readlines()
    translation_map: Dict[str, str] = {}
    pattern = re.compile("([a-zA-Z0-9_\.]+)=(.+)")
    for line in translation_list:
        if match := pattern.match(line):
            k = match[1].strip()
            v = match[2].strip()
            translation_map[k] = v
    return translation_map

# Convertions between "symbolic" ==> "resolved" paths
def resolve_symbolic_path(
        path: Path, rp_paths: Iterable[Path],
        block_images_paths: Iterable[Path]) -> Path:
    '''
    Changes symbolic path to real path that points at a real file in one of
    the resource packs or "block-images" folders. Replaces "RP" with real
    path to the resource pack. Adds file extension.

    :param path: symbolic path to a file. "RP" prefix means "resource pack",
        "block-images" prefix means one of the "block-images" folders.
    :return: true path to a texture file.
    '''
    str_path = path.as_posix()
    suffixes = [".png", ".tga"]
    for path, prefix in chain(
            ((p, "RP/") for p in rp_paths),
            ((p, "block-images/") for p in block_images_paths)):
        if str_path.startswith(prefix):
            curr_path = path / str_path[len(prefix):]
            for suffix in suffixes:
                if curr_path.with_suffix(suffix).exists():
                    return curr_path.with_suffix(suffix)
        for suffix in suffixes:
            if path.with_suffix(suffix).exists():
                return path.with_suffix(suffix)
    raise TextureNotFound(f"Could not find image from path: {path.as_posix()}")

# Access to data
def get_texture_from_texture_map(
        texture_name: str, data: int,
        rp_paths: Iterable[Path], block_images_paths: Iterable[Path],
        texture_map: TextureMap) -> Path:
    '''
    Returns the resolved path to the texture file.

    :param texture_name: name of the item.
    :param data: data of the item.
    :param rp_path: path to the resource pack.
    :param block_images_path: path to the block images folder.
    :param texture_map: texture map object with the texture mapping.
    '''
    try:
        path = Path(texture_map[texture_name][str(data)])
        return resolve_symbolic_path(path, rp_paths, block_images_paths)
    except KeyError:
        raise TextureNotFound(f"Texture '{texture_name}' not found.")

def get_entity_spawn_egg_texture_provider(
        identifier: str, rp_paths: List[Path],
        block_images_paths: Iterable[Path],
        texture_map: TextureMap) -> Callable[[], Image.Image]:
    '''
    Returns a function that returns an image of a spawn egg texture using
    entity definition from resource pack.

    :param identifier: full entity identifier (with namespace).
    :param rp_path: path to the resource pack.
    '''
    for rp_path in rp_paths:
        for entity_path in (rp_path / "entity").glob("**/*.json"):
            try:
                entity_data = load_jsonc(
                    entity_path).data["minecraft:client_entity"]["description"]
                name = entity_data["identifier"]
                if name != identifier:
                    continue
                spawn_egg = entity_data["spawn_egg"]
                if "texture" in spawn_egg:
                    spawn_egg_texture = spawn_egg["texture"]
                    if not isinstance(spawn_egg_texture, str):
                        continue
                    texture_idex = spawn_egg.get("texture_index", 0)
                    texture_path = get_texture_from_texture_map(
                        spawn_egg_texture, texture_idex, rp_paths,
                        block_images_paths, texture_map)
                    return lambda: get_image_from_path(texture_path)
                else:
                    # Try to generate the texture from the base_color adn
                    # overlay_color.
                    # Mc has some weird formats for colors - #123456 and
                    # #0x123456. I hope it doesn't use alpha channel. The
                    # function uses last 6 digits of the color.
                    base_color = hex_to_rgb(spawn_egg.get(
                        "base_color", "#000000")[-6:])
                    overlay_color = hex_to_rgb(spawn_egg.get(
                        "overlay_color", "#000000")[-6:])
                    overlay_path = find_existing_subpath(
                        rp_paths, "textures/items/spawn_egg_overlay.png")
                    base_path = find_existing_subpath(
                        rp_paths, "textures/items/spawn_egg.png")
                    return lambda: generate_spawn_egg_from_colors(
                        base_color, overlay_color, base_path, overlay_path)
            except (
                    LookupError, TypeError, ValueError,FileNotFoundError,
                    json.JSONDecodeError) as e:
                logging.warning(
                    f"Failed to load entity data from"
                    f" {entity_path.as_posix()}")
                continue
    raise TextureNotFound(
        f"Unable to find texture name of spawn egg of {identifier}")

def hex_to_rgb(hex_string: str) -> ColorTuple:
    rgba = []
    for i in (0, 2, 4):
        decimal = int(hex_string[i:i + 2], 16)
        rgba.append(decimal)
    # adding an alpha channel with 255 for no transparency
    rgba.append(255)
    return tuple(rgba)  # type: ignore

def generate_spawn_egg_from_colors(
        base_color: ColorTuple, overlay_color: ColorTuple, base_path: Path,
        overlay_path: Path) -> Image.Image:
    '''
    Generates an image of a spawn egg from base and overlay colors and paths.

    :param base_color: the base color of the spawn egg
    :param overlay_color: the overlay color of the spawn egg
    :param base_path: path to the base texture
    :param overlay_path: path to the overlay texture
    '''
    with Image.open(base_path) as img:
        img.load()
        base_img = img
    base_img = ImageChops.multiply(
        base_img, Image.new("RGBA", base_img.size, base_color))
    with Image.open(overlay_path) as img:
        img.load()
        overlay_img = img
    overlay_img = ImageChops.multiply(
        overlay_img, Image.new("RGBA", overlay_img.size, overlay_color))
    base_img.paste(overlay_img, (0, 0), overlay_img)
    return base_img

def get_image_from_path(path: Path) -> Image.Image:
    '''
    Returns an image from path.

    :param path: the path to the image:
    '''
    if not path.exists():
        raise TextureNotFound(f"File not found: {path.as_posix()}")
    with Image.open(path) as img:
        img.load()
        result = img.convert("RGBA")
    return result