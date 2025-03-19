'''
Project defines the Project class that is used to handle main functionality of
the application.
'''
from dataclasses import dataclass
import logging
from typing import Any, Callable, Dict, Generator, List, NewType, Optional, cast
from pathlib import Path
import json
import re
from PIL import Image
import shutil
from functools import cache

from .cache import get_app_data_path
from .recipe_objects import (
    Recipe, RecipeBrewing, RecipeCrafting, RecipeFurnace, RecipeKey, ActorIdWildcard,
    InvalidRecipeException, load_recipe)
from .utils import (
    TextureMap, TextureNotFound, get_entity_spawn_egg_texture_provider,
    get_texture_from_texture_map, texture_map_from_hardcoded,
    texture_map_from_rp, lang_file, find_existing_subpath, better_wrap)
from .image import (
    OptPath, Subimage, SubimageText, get_custom_image,
    paste_subimage, paste_subimagetext, paste_that_works)
from better_json_tools import load_jsonc
from better_json_tools.json_walker import JSONWalker
from .utils import get_image_from_path


# The scanner used for analysing the text property of the templates
# WARNING: The capturing groups don't work as expected. DO NOT USE THEM IN THE
# PATTERNS. If you want to extract data from the tokens, match the token outside
# of the Scanner object.
counter_pattern = r'\$counter\.([A-Za-z_][A-Za-z0-9_]*)(?:\:([1-9][0-9]*))?(?:\:(\+?\d+|\-\d+))?'
counter_barces_pattern = r'\$\{counter\.([A-Za-z_][A-Za-z0-9_]*)(?:\:([1-9][0-9]*))?(?:\:(\+?\d+|\-\d+))?\}'
last_recipe_pattern = r'\$last_recipe\.([A-Za-z_][A-Za-z0-9_]*)'
last_recipe_braces_pattern = r'\$\{last_recipe\.([A-Za-z_][A-Za-z0-9_]*)\}'
var_pattern = r'\$var\.([A-Za-z_][A-Za-z0-9_]*)'
var_braces_pattern = r'\$\{var\.([A-Za-z_][A-Za-z0-9_]*)\}'
text_pattern = r'[^\$]+'
text_dollar_pattern = r'\$'
TEXT_SCANNER = re.Scanner([  # type: ignore
    # Couter
    (counter_pattern, lambda scanner, token: ('COUNTER', token)),
    (counter_barces_pattern, lambda scanner, token: ('COUNTER_BRACES', token)),  # With braces
    # Last recipe
    (last_recipe_pattern, lambda scanner, token: ('LAST_RECIPE_PROPERTY', token)),
    (last_recipe_braces_pattern, lambda scanner, token: ('LAST_RECIPE_PROPERTY_BRACES', token)),  # With braces
    # Var
    (var_pattern, lambda scanner, token: ('VAR_PROPERTY', token)),
    (var_braces_pattern, lambda scanner, token: ('VAR_PROPERTY_BRACES', token)),  # With braces
    # Just a plain text
    (text_pattern, lambda scanner, token: ('TEXT', token)),
    (text_dollar_pattern, lambda scanner, token: ('TEXT_DOLLAR', token)),
])

def resolve_text(
        text: str, counters: Dict[str, int],
        recipe_properties: None | Dict[str, Any],
        scope: dict[str, Any] | None) -> str:
    '''
    Resolve text is a function that takes a text and some scopes of variables
    as an input and resolves the text to a string. It's used for image names
    in the "image" foreground item (in "background" property) and in "text"
    foreground item (in "text" property).

    :param text: The text to be resolved.
    :param counters: A  dictionary of counters. The key is the name of the
        counter and the value is the current value of the counter.
    :param recipe_properties: A dictionary of properties of the last recipe.
        This is not the same as recipe_properties in some other functions.
        It contains the properties of the last recipe ONLY!
    '''
    tokenized_text, reminder = TEXT_SCANNER.scan(text)
    if reminder != '':
        logging.warning(f"Could not parse text: {text}")
    else:
        text = ""
        token: tuple[str, str]
        for token in tokenized_text:
            if token[0] in ["COUNTER", "COUNTER_BRACES"]:
                if token[0] == "COUNTER":
                    token_match = re.fullmatch(counter_pattern, token[1])
                else:
                    token_match = re.fullmatch(
                        counter_barces_pattern, token[1])
                counter_name = token_match[1]
                try:
                    counter_start = int(token_match[2])
                except (ValueError, TypeError):
                    counter_start = 1
                # Offset value
                offset_value = 0
                if token_match[3]:
                    try:
                        offset_value = int(token_match[3])
                    except ValueError:
                        pass
                if counter_name not in counters:
                    counters[counter_name] = counter_start
                value = counters[counter_name]
                counters[counter_name] = value + 1 + offset_value
                text += str(value + offset_value)
            elif token[0] in ["TEXT", "TEXT_DOLLAR"]:
                text += token[1]
            elif token[0] in [
                    "LAST_RECIPE_PROPERTY", "LAST_RECIPE_PROPERTY_BRACES"]:
                if token[0] == "LAST_RECIPE_PROPERTY":
                    token_match = re.fullmatch(
                        last_recipe_pattern, token[1])
                else:
                    token_match = re.fullmatch(
                        last_recipe_braces_pattern, token[1])
                # If the last recipe is "" then entire text shouldn't
                # be rendered. Return empty string.
                if recipe_properties is None:
                    text = ""
                    break
                val = recipe_properties.get(token_match[1], "")
                if isinstance(val, list):
                    val = "\n".join(str(v) for v in val)
                text += str(val)
            elif token[0] in ["VAR_PROPERTY", "VAR_PROPERTY_BRACES"]:
                if token[0] == "VAR_PROPERTY":
                    token_match = re.fullmatch(var_pattern, token[1])
                else:
                    token_match = re.fullmatch(var_braces_pattern, token[1])
                if scope is None:
                    text = ""
                    break
                val = scope.get(token_match[1], "")
                if isinstance(val, list):
                    val = "\n".join(str(v) for v in val)
                text += str(val)
            else:  # This should never happen unless new tokens are added
                logging.warning(
                    f"Unknown token: {token} in text:\n{text}")
                text += token[1]
    return text

# The scanner used for analysing the pattern used for naming the output file.
OUTPUT_NAME_SCANNER = re.Scanner([  # type: ignore
    # Recipe name
    (r'\$last_recipe_name', lambda scanner, token: ('RECIPE_NAME', scanner.match)),
    (r'\$\{last_recipe_name\}', lambda scanner, token: ('RECIPE_NAME', scanner.match)),  # With braces
    # Recipe namespace
    (r'\$last_recipe_namespace', lambda scanner, token: ('RECIPE_NAMESPACE', scanner.match)),
    (r'\$\{last_recipe_namespace\}', lambda scanner, token: ('RECIPE_NAMESPACE', scanner.match)),  # With braces
    # Template name
    (r'\$template_name', lambda scanner, token: ('TEMPLATE_NAME', scanner.match)),
    (r'\$\{template_name\}', lambda scanner, token: ('TEMPLATE_NAME', scanner.match)),  # With braces
    # Just a plain text
    (r'[^\$]+', lambda scanner, token: ('TEXT', token)),
    (r'\$', lambda scanner, token: ('TEXT', token)),
])


def resolve_output(
        output_name_pattern: str,
        recipe_name: str | None,
        recipe_namespace: str | None,
        template_name: str) -> str:
    '''
    Resolve the output_file_name property of a template.

    :param output_name_pattern: The pattern to be resolved.
    :param recipe_name: The name of the last recipe used. Can be None, in which
        case the name will be replaced with 'unknown'.
    :param recipe_namespace: The namespace of the last recipe used. Can be
        None, in which case the namespace will be replaced with 'unknown'.
    :param template_name: The name of the template used.
    '''
    # Parse the pattern and return the output file name
    tokenized_text, reminder = OUTPUT_NAME_SCANNER.scan(  # type: ignore
        output_name_pattern)
    if reminder != '':
        logging.warning(f"Could not parse text: {output_name_pattern}")
    tokenized_text = cast(list[tuple[str, str]], tokenized_text)
    text: str = ""
    token: tuple[str, str]
    for token in tokenized_text:
        if token[0] == "RECIPE_NAME":
            if recipe_name is None:
                logging.warning(
                    "The name of the file contains a reference to the "
                    "name of the last recipe, but the last recipe is "
                    "unknown. The name of the last recipe will be "
                    "replaced with 'unknown'.")
                text += 'unknown'
            else:
                text += recipe_name
        elif token[0] == "RECIPE_NAMESPACE":
            if recipe_namespace is None:
                logging.warning(
                    "The name of the file contains a reference to the "
                    "namespace of the last recipe, but the last recipe is "
                    "unknown. The namespace of the last recipe will be "
                    "replaced with 'unknown'.")
                text += 'unknown'
            else:
                text += recipe_namespace
        elif token[0] == "TEMPLATE_NAME":
            text += template_name
        elif token[0] == "TEXT":
            text += token[1]
        else:  # This should never happen unless new tokens are added
            logging.warning(
                f"Unknown token: {token} in output_file_name")
            text += token[1]
    return text

RunActions = Generator[Callable[[], None], None, None]


# Function for gettings paths to textures interactively
# Inputs: item_name: str, data: int, recipe_name: str
# Output: Path
# The recipe_name is used for error messages.
InteractivetextureGetter = Callable[[str, int, str], Path]

class Project:
    def __init__(self) -> None:
        self.behavior_pack: Path = None
        self.resource_pack: Path = None
        self.global_data: Path = get_app_data_path() / "data"
        self.local_data: Path = None
        self.template = "custom_template"
        self.scale = 1  # Additional scale multiplayer for generated images

        # Used for naming the output files, reset on every run
        self.image_number = 0

        # List of functions that can be sued by the Project to get the paths
        # to the textures interactively
        self.interactive_texture_getters: List[InteractivetextureGetter] = []


    def load_template(self, name: str | None = None) -> JSONWalker:
        if name is None:
            name = self.template
        return load_template(
            name,
            self.local_data / "templates",
            self.global_data / "templates")

    def yield_book_creation_aciton(self, recipe_paths: list[Path]) -> RunActions:
        '''
        Yields the actions that generate textures for the book. A book can be
        based on one of the following template types:
        - a book template
        - a page template.

        If the the template is a page than it yields from the
        "yield_page_creation_action" function.

        :param template: The template used to generate the images.
        :param recipe_paths: The list of the paths to the recipe files.
        '''
        # Reset the image number
        self.image_number = 0
        # Load the template
        template = self.load_template()
        # Load the recipes into a list
        recipes: List[Recipe] = []
        for path in recipe_paths:
            try:
                recipes.append(load_recipe(path))
            except InvalidRecipeException as e:
                logging.warning(f"Skipping {path}: {e}")

        # Create the output directory if it doesn't exist
        output = self.local_data / "generated-images"
        output.mkdir(exist_ok=True, parents=True)
        # Get the scope variables
        counters, recipe_properties = self.get_scopes()
        # Check if it's a page template or a book template
        pages = template / "pages"
        if not pages.exists:
            # PAGE TEMPLATE
            yield from self.yield_page_creation_actions(
                template, recipes, output, counters, recipe_properties)
        else:
            # BOOK TEMPLATE
            if not isinstance(pages.data, list):
                raise ValueError(
                    "The 'pages' property of the template must be a list.")
            for page in pages // int:
                page_path = page / "page"
                if page_path.exists:
                    # REFERENCE TO ANOTHER FILE
                    # Check for extra recipe_patterns for this page
                    recipe_pattern_walker = page / "recipe_pattern"
                    recipe_pattern: str | None
                    if recipe_pattern_walker.exists:
                        recipe_pattern = recipe_pattern_walker.data
                        if not isinstance(recipe_pattern, str):
                            raise ValueError(
                                "The 'recipe_pattern' property of the page "
                                "must be a string.")
                    else:
                        recipe_pattern = None
                    scope: dict = page.data.get("scope", {})
                    if not isinstance(scope, dict):
                        raise ValueError(
                            "The 'scope' property of the page must be a dict."
                        )
                    # Load the other file
                    if not isinstance(page_path.data, str):
                        raise ValueError(
                            "The 'page' property of the page must be a string "
                            "with a reference to an existing template.")
                    page = self.load_template(page_path.data)
                    yield from self.yield_page_creation_actions(
                        page, recipes, output, counters, recipe_properties,
                        recipe_pattern=recipe_pattern, scope=scope)
                else:
                    # A PAGE DEFINITION INSIDE THE LIST
                    yield from self.yield_page_creation_actions(
                        page, recipes, output, counters, recipe_properties)

    def get_scopes(self) -> tuple[dict[str, int], dict[str, Any]]:
        '''
        Helper function that loads the scope dictionaries for loading the
        templates.

        :return: A tuple of two dictionaries - counters and recipe_properties
        '''
        # Data maps used by the templates
        counters: Dict[str, int] = {}
        if (self.local_data / "recipe_properties.json").exists():
            recipe_properties = load_jsonc(
                self.local_data / "recipe_properties.json").data
            if not isinstance(recipe_properties, dict):
                raise ValueError("recipe_properties.json must be a dictionary")
        else:
            recipe_properties = {}
        recipe_properties["last_recipe"] = ""
        return counters, recipe_properties

    # Function / external logic
    def yield_page_creation_actions(
            self,
            template: JSONWalker,
            recipes: list[Recipe],
            output: Path,
            counters: dict[str, int],
            recipe_properties: dict[str, Any],
            recipe_pattern: str | None = None,
            scope: dict[str, Any] | None = None
        ) -> RunActions:
        '''
        Yields the actions that generate textures from a page template.

        :param template: The template of the page.
        :param recipes: The list of the recipes available for the page to use.
        :param output: The path to the directory where the images will be
            saved.
        :param counters: The dictionary that keeps track of the values of the
            counters.
        :param recipe_properties: The dictionary that provides the values of
            properties for the recipes (like descriptions and titles).
        :param recipe_pattern: an extra recipe pattern for filtering out the
            recipes that can be used by this page.
        :param scope: The scope with variables that can be used using the
            $variable.<name> syntax.
        '''
        if scope is None:
            scope: dict[str, Any] = {}
        # Load the templaate
        template_data = template.data
        if not isinstance(template_data, dict):
            raise ValueError("Template must be a dictionary")

        # Get the background image
        background_path: Path | None
        if 'background' in template_data:
            background_dirs = [
                self.local_data / "images",
                self.global_data / "images"]
            background_path = find_existing_subpath(
                background_dirs, template_data['background'])
        else:
            background_path = None

        is_first_tempalte_page = True  # the first page of this template
        while True:
            template_name = self.template.rsplit(".", 1)[0]
            action = self.get_page_creation_action(
                recipes=recipes,
                template=template_data,
                background_path=background_path,
                output=output,
                counters=counters,
                recipe_properties=recipe_properties,
                template_name=template_name,
                force=is_first_tempalte_page,  # force the first page
                page_recipe_pattern=recipe_pattern,
                scope=scope
            )
            is_first_tempalte_page = False
            if action is None:
                break
            yield action

    # internal
    def get_page_creation_action(
            self,
            recipes: List[Recipe],
            template: Dict[str, Any],
            background_path: OptPath,
            output: Path,
            counters: Dict[str, int],
            recipe_properties: Dict[str, Any],
            template_name: str,
            force: bool,
            page_recipe_pattern: str | None,
            scope: dict[str, Any]
        ) -> Optional[Callable[[], None]]:
        '''
        Generates a function which creates an image of a page. If the page
        doesn't contain any recipes, returns None unless the force parameter
        is True.

        :param recipes: A list of recipes in RP. The function will use some
            of the recipes from that list and REMOVE THEM FROM IT.
        :param template: the template that defines the look of the page
        :param background_path: optional path to the background image.
        :param output: the directory where the image should be saved. The name
            is generated from get_page_output_file_name.
        :param counters: a dictionary of the counter variables used for some
            of the page elements. They're incremented every time they're used.
        :param recipe_properties: the dictinary that stores the variables used
            by text items in the pages, and other thins like the name of the
            last recipe used.
        :param template_name: the name of the template file without the
            extension
        :param force: forces the function to return an action even if there
            are no recipes to generate. This is useful for generating the first
            page of a book even if the book doesn't contain any recipes.
        '''
        fg_actions: List[Callable[[str], None]] = []

        # Length of recipes before they may be consumed by
        # get_pag_item_creation_aciton
        old_recipes_len = len(recipes)

        # The true scale of the page (from teplate and GUI modifier)
        scale = self.scale*template.get('scale', 1)

        for page_item in template['foreground']:
            fg_action = self.get_page_item_creation_action(
                recipes, page_item, scale, counters, recipe_properties,
                page_recipe_pattern, scope)
            if fg_action is not None:
                fg_actions.append(fg_action)

        if not force:
            # If no recipes were consumed, no more work to do
            if len(recipes) == old_recipes_len or len(fg_actions) == 0:
                return None

        # Create the main action to return
        self.image_number += 1

        # Because of the insanely confusing logic of this program, we have to
        # thet the current state of recipe_properties["last_recipe"], now
        # to pass it to the closure to get the output_file_name. Using the
        # recipe_properties["last_recipe"] in the closure wouldn't work because
        # at that point it's already changed to the last result (or maybe some
        # other result (?)).
        last_recipe = recipe_properties["last_recipe"]

        image_number = self.image_number  # Pass current state to the closure
        def action():
            background = get_custom_image(
                image_size=template.get('size'),
                scale=scale,
                background=background_path,
                subimages=[])
            for fg_action in fg_actions:
                try:
                    fg_action(background)  # paste foreground images
                except TextureNotFound as e:
                    logging.warning(f"{e}")
            output_file_name = self.get_page_output_file_name(
                last_recipe, template, template_name, recipe_properties,
                counters, scope)
            background.save(output / f"{image_number:04}_{output_file_name}")
        return action

    # internal
    def get_page_output_file_name(
            self,
            last_recipe: str,
            template: Dict[str, Any],
            template_name: str,
            recipe_properties: Dict[str, Any],
            counters: Dict[str, int],
            scope: dict[str, Any]
            ) -> str:
        '''
        Returns the name of the file to be generated based on the data provided
        in the template and the page number. The page number is not incremented
        after this function is called. The results always start with the
        page number with preceding zeros to make the number at least 4 digits
        for easier sorting.

        :param tempalte: loaded template file
        :param template_name: the name of the template file without the
            extension
        :param recipe_properties: the dictionary with the properties of the
            recipes.
        '''
        # Get the name and namespace of the last_recipe
        recipe_namespace: str | None = None
        recipe_name: str | None = None
        if ":" in last_recipe:
            recipe_namespace, recipe_name = last_recipe.split(":", 1)
        else:
            recipe_namespace = "minecraft"
            recipe_name = last_recipe
        # Get output_file_name property of the template
        output_name_pattern = r"${template_name}"
        if "output_file_name" in template:
            if isinstance(template["output_file_name"], str):
                output_name_pattern = template["output_file_name"]
            else:
                logging.warning(
                    f"output_file_name is not a string, using default")

        # Resolve the text ofr the 'text' part of the output file name
        text = resolve_output(
            output_name_pattern, recipe_name, recipe_namespace, template_name)
        # Resolve again to add counters and variables
        curr_recipe_properties: dict[str, Any] = (  # type: ignore
            recipe_properties.get(last_recipe, {})  
            if last_recipe != ""
            else {}
        )
        text = resolve_text(
            text, counters, curr_recipe_properties, scope)
        # Return with the image number generated in front of the text
        return (f"{text}.png").strip()

    # internal
    def get_page_item_creation_action(
            self, recipes: List[Recipe], page_object: Dict[str, Any],
            page_scale: int, counters: Dict[str, int],
            recipe_properties: Dict[str, Any],
            page_recipe_pattern: str | None,
            scope: dict[str, Any]
    ) -> Optional[Callable[[Image.Image], None]]:
        '''
        Generates a function which creates a single element of a page (single
        recipe/image/textfield) and pastes it onto it (onto the background).
        The "background" is an argument of the returned function. If the
        page_object type is a recipe and there is no recipes left, returns
        None.

        :param recipes: A list of available recipes. If the page_object is
            a recipe type it can use and remove items from this list.
        :param page_object: the info about the object to paste on the page
        :param page_scale: the scale of the page. It affects the poperties of
            the page_object. The offset and size are multiplied by this scale.
        :param counters: a dictionary of counters. If the page_object is a
            text type and uses a counter syntax, it will use the counter
            value from this dictionary and increment it.
        :param recipe_properties: a dictionary of properties of the recipes.
        :param page_recipe_pattern: additional pattern for matching recipes
            provided by the page that this item is on. It's optional and if
            it's None it will be ignored.
        :param scope: a dictionary of variables that can be used in the
            page_object. It's defined in the book that refers to this page.
        '''
        # Return different closure based on 'item_type' of the page_object
        image_dirs = [
            self.local_data / "images",
            self.global_data / "images"]
        font_dirs = [
            self.local_data / "fonts",
            self.global_data / "fonts"]

        item_type = page_object['item_type']
        recipe_page_items = (
            "recipe_shaped", "recipe_furnace", "recipe_brewing",
            "recipe_any")
        if item_type in recipe_page_items:
            # Find a recipe that matches the pattern specified in the
            # page_object
            accept_shaped = item_type == "recipe_shaped"
            accept_furnace = item_type == "recipe_furnace"
            accept_brewing = item_type == "recipe_brewing"
            if item_type == "recipe_any":
                accept_furnace = "recipe_furnace" in page_object
                accept_shaped = "recipe_shaped" in page_object
                accept_brewing = "recipe_brewing" in page_object

            # Find the first accepted recipe
            recipe_pattern = re.compile(page_object['recipe_pattern'])
            for i, recipe in enumerate(recipes):
                if isinstance(recipe, RecipeCrafting) and not accept_shaped:
                    continue
                if isinstance(recipe, RecipeFurnace) and not accept_furnace:
                    continue
                if isinstance(recipe, RecipeBrewing) and not accept_brewing:
                    continue
                if recipe_pattern.fullmatch(recipe.name):
                    # If the page recipe pattern is provided it also has to
                    # match
                    if page_recipe_pattern is None:
                        break
                    page_recipe_pattern_re = re.compile(page_recipe_pattern)
                    if page_recipe_pattern_re.fullmatch(recipe.name):
                        break
            else:
                recipe_properties["last_recipe"] = ""
                return None  # Item not found (no action to return)

            recipe_properties["last_recipe"] = recipe.name
            # Consume the recipe that matched and save it in variable for closure
            recipe = recipes.pop(i)
            if isinstance(recipe, RecipeCrafting):
                if item_type == "recipe_any":
                    page_object = page_object["recipe_shaped"]
                return self.get_crafting_page_item_action(
                    recipe, page_object, page_scale, image_dirs)
            elif isinstance(recipe, RecipeFurnace):
                if item_type == "recipe_any":
                    page_object = page_object["recipe_furnace"]
                return self.get_furnace_page_item_action(
                    recipe, page_object, page_scale, image_dirs)
            elif isinstance(recipe, RecipeBrewing):
                if item_type == "recipe_any":
                    page_object = page_object["recipe_brewing"]
                return self.get_brewing_page_item_action(
                    recipe, page_object, page_scale, image_dirs)
            else:
                raise RuntimeError("Unreachable code")
        elif item_type == "image":
            ptp = None  # padding thumbnail properties
            if 'size' in page_object:
                ptp = {
                    "width": page_object['size'][0],
                    "height": page_object['size'][1]
                }
            # Get the recipe properties of the last recipe for this closure
            last_recipe = recipe_properties["last_recipe"]
            curr_recipe_properties = (
                recipe_properties.get(last_recipe, {})
                if last_recipe != ""
                else {}
            )

            # Return the action closure
            def action(background: Image.Image):
                '''Pastes the image onto the background'''
                # Find the path to the image. It must be done in the closure
                # resolving the text could change the counters even if the
                # image is not rendered
                subpath = resolve_text(
                    page_object['image'], counters,
                    curr_recipe_properties, scope)
                if subpath == "":
                    return  # Failed to resolve the text
                try:
                    image_path = find_existing_subpath(
                        image_dirs, subpath)
                except FileNotFoundError as e:
                    logging.warning(f"Unable to find image:\n{e}")
                    return
                # There is no guarantee that the image exist so this action
                # sometimes can just return without doing anything
                paste_subimage(
                    image=background,
                    scale=page_scale,
                    subimage=Subimage(
                        x=page_object['offset'][0],
                        y=page_object['offset'][1],
                        scale=page_object.get('scale', 1),
                        image_provider=lambda: get_image_from_path(image_path),
                        padding_thumbnail_properties=ptp)
                )
            return action
        elif item_type == "text":
            # Find the path to the font
            font_path = find_existing_subpath(
                font_dirs, page_object['font']).absolute().as_posix()
            color = page_object.get('color', (255, 255, 255, 255))
            color = tuple(color)  # Font function doens't accept list
            alignment = page_object.get('alignment', "left")
            if alignment not in ["left", "center", "right"]:
                raise ValueError(f"Unknown alignment type: '{alignment}'")

            # Get the recipe properties of the last recipe for this closure
            last_recipe = recipe_properties["last_recipe"]
            curr_recipe_properties = (
                recipe_properties.get(last_recipe, {})
                if last_recipe != ""
                else {}
            )

            # Return the action closure
            def action(background: Image.Image):
                '''Pastes the text onto the background'''
                # Text must be resolved in the action because otherwise
                # pages that aren't rendered could increment the counters
                text = page_object['text']
                if isinstance(text, list):
                    text = "\n".join(text)
                text = resolve_text(
                    text, counters, curr_recipe_properties, scope)
                # Text wrapping
                if 'line_length' in page_object:
                    line_length = page_object['line_length']
                    if not isinstance(line_length, int):
                        raise ValueError(f"line_length must be an integer")
                    text = better_wrap(text, width=line_length)
                # scale=page_object.get('scale', 12)
                # color=page_object.get('color', (255, 255, 255, 255))
                paste_subimagetext(
                    image=background,
                    scale=page_scale,
                    subimage_text=SubimageText(
                        text=text,
                        x=page_object['offset'][0],
                        y=page_object['offset'][1],
                        scale=page_object.get('scale', 12),
                        font=font_path,
                        color=color,
                        alignment=alignment,
                        anchor=page_object.get('anchor', 'la'),
                        spacing=page_object.get('spacing', 1.0),
                        anti_alias=page_object.get('anti_alias', False))
                )
            return action
        else:
            raise ValueError("Unknown foreground item type")

    # internal
    def get_crafting_page_item_action(
            self, recipe: RecipeCrafting, page_object: Dict[str, Any],
            page_scale: int, image_dirs: List[Path]
    ) -> Optional[Callable[[Image.Image], None]]:
        scaled_offset = (
            page_object['offset'][0]*page_scale,
            page_object['offset'][1]*page_scale)
        # Implementing the result as closure delays some of the work

        def action(background: Image.Image):
            '''Pastes the image of the recipe onto the background'''
            # Get the paths to the textures of the ingredients of the recipe
            item_texture_providers: Dict[str, Callable[[], Image.Image]] = {}
            for i, row in enumerate(recipe.pattern):
                for j, key in enumerate(row):
                    if key == " ":
                        continue
                    item_texture_providers[
                        f'{i},{j}'
                    ] = get_image_provider(
                        recipe.keys[key], recipe.name,
                        self.behavior_pack, self.resource_pack, self.local_data,
                        self.interactive_texture_getters)
            # If recipe uses the result find the path for its texture as well
            if 'result' in page_object["items"]:
                crafting_result_texture_path = get_image_provider(
                    recipe.result, recipe.name,
                    self.behavior_pack, self.resource_pack, self.local_data,
                    self.interactive_texture_getters)
                item_texture_providers["result"] = crafting_result_texture_path

            # Get the real background path
            if 'background' in page_object:
                true_background_path = find_existing_subpath(
                    image_dirs, page_object['background'])
            else:
                true_background_path = None

            # Create the subimage objects from the paths and the
            # definitions of the item placement from the template
            subimages: List[Subimage] = []
            for k, item in page_object["items"].items():
                if k not in item_texture_providers:
                    continue  # Sometimes some slots are empty
                subimages.append(Subimage(
                    x=item['offset'][0],
                    y=item['offset'][1],
                    scale=1,
                    image_provider=item_texture_providers[k],
                    padding_thumbnail_properties={
                        "width": item['size'][0],
                        "height": item['size'][1],
                        "align_y": "bottom"
                    },
                    alpha_clip=False,
                ))
            foreground = get_custom_image(
                image_size=page_object.get('size', None),
                scale=page_object.get('scale', 1)*page_scale,
                background=true_background_path,
                subimages=subimages)
            paste_that_works(background, foreground, scaled_offset)
        return action

    # internal
    def get_furnace_page_item_action(
            self, recipe: RecipeFurnace, page_object: Dict[str, Any],
            page_scale: int, image_dirs: List[Path]
    ) -> Optional[Callable[[Image.Image], None]]:
        scaled_offset = (
            page_object['offset'][0]*page_scale,
            page_object['offset'][1]*page_scale)
        # Implementing the result as closure delays some of the work

        def action(background: Image.Image):
            '''Pastes the image of the recipe onto the background'''
            item_texture_paths = {}
            if 'input' in page_object["items"]:
                item_texture_paths["input"] = get_image_provider(
                    recipe.input, recipe.name, self.behavior_pack,
                    self.resource_pack, self.local_data,
                    self.interactive_texture_getters)
            if 'output' in page_object["items"]:
                item_texture_paths["output"] = get_image_provider(
                    recipe.output, recipe.name, self.behavior_pack,
                    self.resource_pack, self.local_data,
                    self.interactive_texture_getters)
            # Get the real background path
            if 'background' in page_object:
                true_background_path = find_existing_subpath(
                    image_dirs, page_object['background'])
            else:
                true_background_path = None
            # Create the subimage objects from the paths and the
            # definitions of the item placement from the template
            subimages: List[Subimage] = []
            for k, item in page_object["items"].items():
                if k not in item_texture_paths:
                    continue  # Sometimes some slots are empty
                subimages.append(Subimage(
                    x=item['offset'][0],
                    y=item['offset'][1],
                    scale=1,
                    image_provider=item_texture_paths[k],
                    padding_thumbnail_properties={
                        "width": item['size'][0],
                        "height": item['size'][1],
                        "align_y": "bottom"
                    },
                    alpha_clip=False,
                ))
            foreground = get_custom_image(
                image_size=page_object.get('size', None),
                scale=page_object.get('scale', 1)*page_scale,
                background=true_background_path,
                subimages=subimages)
            paste_that_works(background, foreground, scaled_offset)
        return action

    # internal
    def get_brewing_page_item_action(
            self, recipe: RecipeBrewing, page_object: Dict[str, Any],
            page_scale: int, image_dirs: List[Path]
    ) -> Optional[Callable[[Image.Image], None]]:
        scaled_offset = (
            page_object['offset'][0]*page_scale,
            page_object['offset'][1]*page_scale)
        # Implementing the result as closure delays some of the work

        def action(background: Image.Image):
            '''Pastes the image of the recipe onto the background'''
            item_texture_paths = {}
            if 'input' in page_object["items"]:
                item_texture_paths["input"] = get_image_provider(
                    recipe.input, recipe.name, self.behavior_pack,
                    self.resource_pack, self.local_data,
                    self.interactive_texture_getters)
            if 'output' in page_object["items"]:
                item_texture_paths["output"] = get_image_provider(
                    recipe.output, recipe.name, self.behavior_pack,
                    self.resource_pack, self.local_data,
                    self.interactive_texture_getters)
            if 'reagent' in page_object["items"]:
                item_texture_paths["reagent"] = get_image_provider(
                    recipe.reagent, recipe.name, self.behavior_pack,
                    self.resource_pack, self.local_data,
                    self.interactive_texture_getters)
            # Get the real background path
            if 'background' in page_object:
                true_background_path = find_existing_subpath(
                    image_dirs, page_object['background'])
            else:
                true_background_path = None
            # Create the subimage objects from the paths and the
            # definitions of the item placement from the template
            subimages: List[Subimage] = []
            for k, item in page_object["items"].items():
                if k not in item_texture_paths:
                    continue  # Sometimes some slots are empty
                subimages.append(Subimage(
                    x=item['offset'][0],
                    y=item['offset'][1],
                    scale=1,
                    image_provider=item_texture_paths[k],
                    padding_thumbnail_properties={
                        "width": item['size'][0],
                        "height": item['size'][1],
                        "align_y": "bottom"
                    },
                    alpha_clip=False,
                ))
            foreground = get_custom_image(
                image_size=page_object.get('size', None),
                scale=page_object.get('scale', 1)*page_scale,
                background=true_background_path,
                subimages=subimages)
            paste_that_works(background, foreground, scaled_offset)
        return action

    # external logic (could be moved outside of this class)
    def get_recipe_paths_list(self) -> List[Path]:
        '''
        Returns a list of all recipe paths to generate images for.
        '''
        paths = list((self.behavior_pack / "recipes").rglob("*.json"))
        return paths

# TODO - This code is a hack. It should be refactored.
# The reason why this function is as it is, is because it used to
# return Path objects so that they could be used later to get the Images
# when the app works in background. The spawn_eggs are generated
# based on data that describes their colors, so returning Path wasn't
# possible because there is no Path to return. Making this
# function return lambda expressions that returns the image was the
# quick and dirty solution that doesn't require refactoring entire code.
def get_image_provider(
        recipe_key: RecipeKey, recipe_name: str,
        behavior_pack: Path, resource_pack: Path, workspace_path: Path,
        interactive_texture_getters: List[InteractivetextureGetter],
        ) -> Callable[[], Image.Image]:
    '''
    Returns a function that returns an Image of a RecipeKey.

    :param recipe_key: the recipe key to get the texture for.
    :param recipe_name: the name of the recipe used for user messages
    '''
    # Lists of RP paths and block-images paths used for some functions::
    rp_paths = [
        resource_pack,
        get_app_data_path() / "data/RP"
    ]
    block_images_paths = [
        workspace_path / "block-images",
        get_app_data_path() / "data/block-images"]

    # Spawn eggs:
    if isinstance(recipe_key.data, ActorIdWildcard):
        return get_entity_spawn_egg_texture_provider(
            recipe_key.data.actor_name,
            rp_paths=rp_paths,
            block_images_paths=block_images_paths,
            texture_map=(
                get_data_map_from_rp(get_app_data_path() / "data/RP") |
                get_data_map_from_rp(resource_pack)
            )
        )
    # Non spawn egg textures:
    # Find the item in behavior pack, then find its icon name and than find
    # the texture based on the icon name.
    try:
        icon_name = get_icon_name(
            recipe_key, behavior_pack, resource_pack)
        result = get_texture_from_texture_map(
            icon_name, recipe_key.data,
            rp_paths=rp_paths,
            block_images_paths=block_images_paths,
            texture_map=(
                get_data_map_from_rp(get_app_data_path() / "data/RP") |
                get_data_map_from_rp(resource_pack)
            )
        )
        return lambda: get_image_from_path(result)
    except TextureNotFound:
        pass
    # Name from hardcoded textures list based on the item name
    try:
        result = get_texture_from_texture_map(
            recipe_key.item, recipe_key.data,
            rp_paths=rp_paths,
            block_images_paths=block_images_paths,
            texture_map=(
                get_data_map(get_app_data_path() / "data/data_map.json") |
                get_data_map(workspace_path / "data_map.json")
            )
        )
        return lambda: get_image_from_path(result)
    except TextureNotFound:
        pass
    # Try to guess the texture
    if get_interactive_mode():
        for texture_getter in interactive_texture_getters:
            try:
                result = texture_getter(
                    recipe_key.item, recipe_key.data, recipe_name)
                save_in_data_map(
                    recipe_key.item, recipe_key.data, result, 
                    resource_pack, workspace_path)
                return lambda: get_image_from_path(result)
            except TextureNotFound:
                pass
    raise TextureNotFound(
        f"Unable to find texture for {recipe_key.item}:{recipe_key.data}")

def initialize_project(workspace_path: Path) -> None:
    '''
    Creates example workspace files to start the project. It creates
    the folders and their contents only if they don't exist.

    :param workspace_path: the path in which the workspace files will be created
    :param behavior_pack: the path to the behavior pack used for generating
        recipe_properties.json file with the list of the properties of the
        that can be added to the generated book.
    '''
    # Copy directories
    example_workspace = get_app_data_path() / "data/example-workspace"
    example_path = example_workspace / "block-images"
    local_path = workspace_path / "block-images"
    if not local_path.exists():
        logging.info(f"Copying {example_path} to {local_path}")
        logging.info(list(example_path.rglob("*")))
        logging.info(list(local_path.rglob("*")))
        shutil.copytree(example_path, local_path)
    example_path = example_workspace / "fonts"
    local_path = workspace_path / "fonts"
    if not local_path.exists():
        logging.info(f"Copying {example_path} to {local_path}")
        shutil.copytree(example_path, local_path)
    example_path = example_workspace / "generated-images"
    local_path = workspace_path / "generated-images"
    if not local_path.exists():
        logging.info(f"Copying {example_path} to {local_path}")
        shutil.copytree(example_path, local_path)
    example_path = example_workspace / "images"
    local_path = workspace_path / "images"
    if not local_path.exists():
        logging.info(f"Copying {example_path} to {local_path}")
        shutil.copytree(example_path, local_path)
    example_path = example_workspace / "templates"
    local_path = workspace_path / "templates"
    if not local_path.exists():
        logging.info(f"Copying {example_path} to {local_path}")
        shutil.copytree(example_path, local_path)
    # Copy files
    example_path = example_workspace / "data_map.json"
    local_path = workspace_path / "data_map.json"
    if not local_path.exists():
        shutil.copy(example_path, workspace_path)

def update_recipe_properties_json(file_path: Path, bp_path: Path):
    # The properties of the items are generated based on the recipes in
    # the project.
    if file_path.exists():
        recipe_properties = load_jsonc(file_path).data
    else:
        recipe_properties = {}
    for path in (bp_path / "recipes").rglob("*.json"):
        try:
            recipe = load_recipe(path)
            if recipe.name not in recipe_properties:
                recipe_properties[recipe.name] = {
                    "description": [],
                    "name": [],
                }
            if "description" not in recipe_properties[recipe.name]:
                recipe_properties[recipe.name]["description"] = []
            if "name" not in recipe_properties[recipe.name]:
                recipe_properties[recipe.name]["name"] = []
        except InvalidRecipeException as e:
            logging.warning(f"Skipping {path}: {e}")
    with file_path.open("w", encoding="utf8") as f:
        json.dump(recipe_properties, f, indent="\t")

def update_recipe_properties_md(source_path: Path, output_path: Path) -> str:
    '''
    Dumps the variables from the recipe_properties.json file into
    a human readable format in recipe_properties.md.

    :param source_path: the path to the recipe_properties.json file
    :param output_path: the path to the recipe_properties.md file

    Returns a success message or raises a ValueError if the
    recipe_properties.json file is not found.
    '''
    if not source_path.exists():
        raise ValueError("Please setup the project first.")
    data = load_jsonc(source_path).data
    output: List[str] = [
        "This file is just a list of the variables from the",
        "recipe_properties.json file. It is not meant to be",
        "modified."
    ]
    for k, v in data.items():
        curr_output: List[str] = []
        is_curr_output_valid = False
        curr_output.append(f"# {k}")
        for kk, vv in v.items():
            curr_output.append(f"## {kk}")
            if isinstance(vv, str):
                curr_output.append(vv)
                is_curr_output_valid = True
            elif isinstance(vv, list) and len(vv) > 0:
                curr_output.extend(vv)
                is_curr_output_valid = True
        curr_output.append("")
        if is_curr_output_valid:
            output.extend(curr_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf8") as f:
        f.write("\n".join(output))
    return f"Variables dumped to {output_path.as_posix()}"

def list_templates(*template_dirs: Path) -> List[str]:
    '''
    Lists templates from given directories. It list all of the JSON files
    found in the given directories.
    '''
    result: List[str] = []
    for template_dir in template_dirs:
        if not template_dir.exists():
            continue
        for path in template_dir.rglob("*.json"):
            result.append(
                path.relative_to(template_dir).with_suffix("").as_posix())
    return result

@cache
def get_data_map(path: Path) -> TextureMap:
    '''
    Returns the data_map.json file from the given path. Returns a dictionary.
    The results are cached, so the file is loaded only once. It's possible
    to modify the contents of returned dictionary because it's cached so
    the changes are preserved. This essentially means that this function
    works like a singleton.

    :param path: the path to the data_map.json file
    '''
    try:
        return texture_map_from_hardcoded(path)
    except:
        return {}

def save_data_map(path: Path) -> None:
    '''
    Saves the data_map.json file to the given path. The data_map.json file
    is generated from the hardcoded data map.

    :param path: the path to the data_map.json file
    '''
    data_map = get_data_map(path)
    with path.open("w", encoding="utf8") as f:
        json.dump(data_map, f, indent=4, sort_keys=True)

@cache
def get_data_map_from_rp(rp_path: Path) -> TextureMap:
    '''
    Returns the data map generated based on a resource pack. The results are
    cached.

    :param rp_path: the path to the resource pack
    '''
    try:
        return texture_map_from_rp(rp_path)
    except:
        return {}

def load_template(template_name: str, *roots: Path) -> JSONWalker:
        '''
        Loads template file with given name. Searches for the file in the
        given roots. Returns the loaded JSON of the first file that matches
        the "{root}/{template_name}.json" pattern.

        :template_name: The name of the temlpate.
        :roots: The directories to search for the template.
        '''
        path = find_existing_subpath(roots, f"{template_name}.json")
        return load_jsonc(path)

def save_in_data_map(
        item_name: str, item_data: int, path: Path,
        rp_path: Path, project_path: Path) -> None:
    '''
    Saves mapping of given item to given path in the appropriate data map with
    appropriate prefix. The item is saved either in global or project data map
    depending on the path. The prefix "RP" or "block-images" is added to the
    path depending on the path pointing on a file in resource pack or in the
    block images directory.

    :param path: the path to the file
    :param item_name: the name of the item
    :param item_data: the data of the item

    :param rp_path: the path to the resource pack
    :param project_path: the path to the project
    '''
    paths: list[tuple[str, Path, Path]] = [
        # (prefix, resovled_path, save_target)
        (
            "RP",
            (rp_path).absolute(),
            project_path / "data_map.json",
        ),
        (
            "RP",
            (get_app_data_path() / "data/RP").absolute(),
            get_app_data_path() / "data/data_map.json",
        ),
        (
            "block-images",
            (project_path / "block-images").absolute(),
            project_path / "data_map.json",
        ),
        (
            "block-images",
            (get_app_data_path() / "data/block-images").absolute(),
            get_app_data_path() / "data/data_map.json",
        ),
    ]
    for prefix, textures_source_path, save_target in paths:
        # Check if path is relatife to source
        if not path.is_relative_to(textures_source_path):
            continue
        # If it's a new item, add the item to the data path (a dict)
        # Every item has a dict keyd with item data values
        if item_name not in get_data_map(save_target):
            get_data_map(save_target)[item_name] = {}
        # Create value to put into the data map (formatted path)
        value = (
            Path(prefix) /
            path.relative_to(textures_source_path).with_suffix("")
        ).as_posix()
        # Put teh value into the data map and save
        get_data_map(save_target)[item_name][str(item_data)] = value
        save_data_map(save_target)
        break  # Found and saved the path
    else:
        raise TextureNotFound(
            f"Path {path.as_posix()} is not relative to RP or"
            " block-images")

def get_icon_name(
        recipe_key: RecipeKey,
        behavior_pack: Path, resource_pack: Path) -> str:
    '''
    Gets the name of the item icon from packs.

    :param recipe_key: object with item's name and data value
    :param behavior_pack: path to the behavior pack
    :param resource_pack: path to the resource pack
    '''
    # Try to get the name from behavior pack
    # (items with format version >= 1.16.100)
    for bp_item in behavior_pack.glob(f"items/**/*.json"):
        try:
            bp_item_data = load_jsonc(bp_item).data
            bp_item_data = bp_item_data["minecraft:item"]
            bp_item_identifier = bp_item_data["description"]["identifier"]
            if bp_item_identifier != recipe_key.item:
                continue
            bp_item_format_version = bp_item_data["format_version"]
            bp_item_format_version = tuple(
                int(i) for i in bp_item_format_version.split("."))
            if bp_item_format_version < (1, 16, 100):
                break  # Only new items store icon in BP
            # Now we can finally find the icon name
            item_icon = bp_item_data[
                "components"]["minecraft:icon"]["texture"]
            if isinstance(item_icon, str):
                return item_icon
        except (
                ValueError, LookupError, AttributeError, TypeError,
                json.JSONDecodeError):
            continue
    # Try to get the name from resource pack
    # (items with format version < 1.16.100)
    rp_paths = [
        resource_pack,
        get_app_data_path() / "data/RP"]
    for rp in rp_paths:
        for rp_item in rp.glob("items/**/*.json"):
            try:
                rp_item_data = load_jsonc(rp_item).data
                rp_item_data = rp_item_data["minecraft:item"]
                rp_item_identifier = rp_item_data["description"]["identifier"]
                if rp_item_identifier != recipe_key.item:
                    continue
                item_icon = rp_item_data["components"]["minecraft:icon"]
                if isinstance(item_icon, str):
                    return item_icon
            except (
                    ValueError, LookupError, AttributeError, TypeError,
                    json.JSONDecodeError):
                continue
    raise TextureNotFound(
        f"Unable to find the icon name for item "
        f"{recipe_key.item}:{recipe_key.data}")


# TODO - replace this with better solution
@dataclass
class GlobalSettings:
    interactive_mode: bool = True

@cache
def _get_global_settings() -> GlobalSettings:
    return GlobalSettings()

def set_interactive_mode(value: bool) -> None:
    _get_global_settings().interactive_mode = value

def get_interactive_mode() -> bool:
    return _get_global_settings().interactive_mode
