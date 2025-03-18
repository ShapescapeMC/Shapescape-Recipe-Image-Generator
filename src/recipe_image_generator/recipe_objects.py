'''
Recipe objects module provides classes for representing the data of the
recipes.
'''
import logging
from typing import NamedTuple, Dict, List, Union, Literal, cast
from pathlib import Path
import re

from better_json_tools import load_jsonc, JSONWalker

# Gets the name of an entity for certain molang query
ACTOR_ID_WILDCARD_REGEX = re.compile(
    r"(?:(?:query)|(?:q))\.get_actor_info_id\('([a-zA-Z0-9_]+:[a-zA-Z0-9_]+)'\)")

# A new format of naming spawn eggs without using weird Molang queries
NEW_SPAWN_EGG_REGEX = re.compile(
    r"((?:[a-zA-Z0-9_]+:)?[a-zA-Z0-9_]+)_spawn_egg")

# An item in format that provides both it's name and the data value (e.g
# "stone:1" or "minecraft:stone:1")
ITEM_WITH_DATA_REGEX = re.compile(
    r"((?:[a-zA-Z0-9_]+:)?[a-zA-Z0-9_]+):([1-9][0-9]*)"
)

class InvalidRecipeException(Exception):
    '''Exception for invalid recipe files'''

class ActorIdWildcard(NamedTuple):
    actor_name: str

class RecipeKey:
    def __init__(self, walker: JSONWalker):
        if not walker.exists:
            raise InvalidRecipeException("Recipe key data doesn't exist")

        # Convert the data to a dict
        if isinstance(walker.data, str):
            if match := ITEM_WITH_DATA_REGEX.fullmatch(walker.data):
                item = match[1]
                data = int(match[2])
                walker.data = {"item": item, "data": data}
            else:
                walker.data = {"item": walker.data}
        
        # Handle the walker data as a dict
        if not isinstance(walker.data, dict):
            raise InvalidRecipeException(
                "Recipe 'key' instance is not a dict or str")
        # The 'item' and 'data' properties
        item_walker = walker / "item"
        if not item_walker.exists or not isinstance(item_walker.data, str):
            raise InvalidRecipeException(
                "Recipe 'key' property 'item' is not a string")
        if match := NEW_SPAWN_EGG_REGEX.fullmatch(item_walker.data):
            # CASE: spawn egg
            self.item = "minecraft:spawn_egg"
            item_data = match[1]
            if ":" not in item_data:
                item_data = f"minecraft:{item_data}"
            self.data: Union[int, ActorIdWildcard] = ActorIdWildcard(item_data)
        elif match := ITEM_WITH_DATA_REGEX.fullmatch(item_walker.data):
            # CASE: item with data
            self.item = match[1]
            self.data = int(match[2])
            if "data" in walker.data:
                raise InvalidRecipeException(
                    "Recipe key is ambiguous, providing the data value both "
                    "in the item name and the data property.")
        else:
            # CASE: other items
            if ":" not in item_walker.data:
                item_walker.data = f"minecraft:{item_walker.data}"
            self.item = item_walker.data
            self.data = self._load_data(walker)

    def _load_data(self, walker: JSONWalker) -> Union[int, ActorIdWildcard]:
        data_walker = walker / "data"
        if not data_walker.exists:
            return 0
        if isinstance(data_walker.data, int):
            return data_walker.data
        if not isinstance(data_walker.data, str):
            raise InvalidRecipeException(
                "Recipe 'key' property 'data' is not a string or int")
        if match := ACTOR_ID_WILDCARD_REGEX.fullmatch(data_walker.data):
            if self.item != "minecraft:spawn_egg":
                raise InvalidRecipeException(
                    "The ActorIdWildcard is only supported for "
                    f"'minecraft:spawn_egg' not {self.item}")
            return ActorIdWildcard(match[1])
        else:  # Could be a string that is a number
            try:
                return int(data_walker.data)
            except ValueError:
                pass  # An error will be raised later
        raise InvalidRecipeException(
            "Recipe 'key' property 'data' is not an int or a ActorIdWildcard")

class RecipeCrafting:
    def __init__(
            self, recipe: JSONWalker, recipe_type: Literal['shaped', 'shapeless']):
        if recipe_type == 'shaped':
            self.name = self._load_name(recipe)
            self.pattern = self._load_pattern(recipe)
            self.result = self._load_result(recipe)
            self.keys = self._load_keys(recipe)
        elif recipe_type == 'shapeless':
            self.name = self._load_name(recipe)
            self.pattern = self._fake_pattern_from_ingredients(recipe)
            self.result = self._load_result(recipe)
            self.keys = self._fake_keys_from_ingredients(recipe)
        else:
            raise ValueError(
                "Invalid recipe type - expected 'shaped' or 'shapeless' but "
                f"got {recipe_type}")

    def _fake_pattern_from_ingredients(self, recipe: JSONWalker) -> List[str]:
        ingredients = recipe / "ingredients"
        if not ingredients.exists or not isinstance(ingredients.data, list):
            raise InvalidRecipeException(
                "Recipe 'ingredients' property is not a list")
        pattern = [
            [' ', ' ', ' '],
            [' ', ' ', ' '],
            [' ', ' ', ' '],
        ]
        keys = []
        for ingredient_key, ingredient in enumerate(ingredients.data):
             # Convert short form (str) to full form {item: str}
            if isinstance(ingredient, str):
                ingredient = {"item": ingredient}
            elif not isinstance(ingredient, dict):
                raise InvalidRecipeException(
                    "Recipe 'ingredients' property is not a list of strings "
                    "or dicts.")
            for i in range(ingredient.get("count", 1)):
                keys.append(str(ingredient_key))
        if len(keys) > 9:
            raise InvalidRecipeException(
                "Shapeless recipes can have at most 9 ingredients."
                "Ingredients that use the 'count' property greater than 1 "
                "are couted as multiple ingredients.")
        for i in range(3):
            for j in range(3):
                index = i * 3 + j
                if index < len(keys):
                    pattern[i][j] = keys[index]
                else:
                    break
        str_pattern: List[str] = []
        for i in range(3):
            str_pattern.append("".join(pattern[i]))
        return str_pattern

    def _fake_keys_from_ingredients(self, recipe: JSONWalker) -> Dict[str, RecipeKey]:
        # KEYS: self.keys
        ingredients = recipe / "ingredients"
        if not ingredients.exists or not isinstance(ingredients.data, list):
            raise InvalidRecipeException("Recipe 'ingredients' property is not a list")
        if len(ingredients.data) > 9:
            raise InvalidRecipeException("Shapeless recipes can have at most 9 ingredients")
        recipe_keys: Dict[str, RecipeKey] = {}
        for i, v in enumerate(ingredients // int):
            recipe_keys[str(i)] = RecipeKey(v)
        return recipe_keys

    def _load_name(self, recipe: JSONWalker) -> str:
        name = recipe / "description" / "identifier"
        if not name.exists or not isinstance(name.data, str):
            raise InvalidRecipeException("Recipe name is not a string")
        return name.data

    def _load_pattern(self, recipe: JSONWalker) -> List[str]:
        pattern = recipe / "pattern"
        # Check if pattern is 3x3 list, if it's not make it one if possible by
        # padding with spaces
        if not pattern.exists or not isinstance(pattern.data, list):
            raise InvalidRecipeException("Pattern is not a list")
        if len(pattern.data) > 3:
            raise InvalidRecipeException("Pattern is not 3x3")
        elif len(pattern.data) < 3:
            for _ in range(len(pattern.data), 3):
                pattern.data.append("   ")
        # Check if pattern is a list of 3-character strings
        for i in range(len(pattern.data)):
            if not isinstance(pattern.data[i], str):
                raise InvalidRecipeException("Pattern raw is not a string")
            if len(pattern.data[i]) > 3:
                raise InvalidRecipeException("Pattern is not 3x3")
            elif len(pattern.data[i]) < 3:
                pattern.data[i] = pattern.data[i].ljust(3)  # Add spaces
        return pattern.data  # type: ignore

    def _load_result(self, recipe: JSONWalker) -> RecipeKey:
        result = recipe / "result"
        if not result.exists:
            raise InvalidRecipeException(
                "Crafting recipe doesn't define the result item.")

        if isinstance(result.data, list):
            if len(result.data) == 0:
                raise InvalidRecipeException(
                    "Crafting recipe doesn't define the result item.")
            elif len(result.data) > 1:
                logging.warning(
                    f'Crafting recipe with identifier "{self.name}" '
                    'defines multiple results. This feature isn\'t currently '
                    'supported. Only the first result will be used.')
            return RecipeKey(result / 0)
        return RecipeKey(result)

    def _load_keys(self, recipe: JSONWalker) -> Dict[str, RecipeKey]:
        keys = recipe / "key"
        if not keys.exists or not isinstance(keys.data, dict):
            raise InvalidRecipeException("Recipe 'key' property is not a dict")
        recipe_keys: Dict[str, RecipeKey] = {}
        for key in keys // str:
            k = cast(str, key.parent_key)
            recipe_keys[k] = RecipeKey(key)
        # Check if patterns use only defined keys
        for p in self.pattern:
            for c in p:
                if c not in recipe_keys and c != " ":
                    raise InvalidRecipeException(
                        f"Pattern '{p}' uses an undefined key '{c}'")
        return recipe_keys

class RecipeFurnace:
    def __init__(self, recipe: JSONWalker):
        name = recipe / "description" / "identifier"
        if not name.exists or not isinstance(name.data, str):
            raise InvalidRecipeException("Recipe name is not a string")
        self.name = name.data

        input = recipe / "input"
        if not input.exists:
            raise InvalidRecipeException("Recipe input is missing")
        self.input = RecipeKey(input)

        output = recipe / "output"
        if not output.exists:
            raise InvalidRecipeException("Recipe output is missing")
        self.output = RecipeKey(output)

class RecipeBrewing:
    def __init__(self, recipe: JSONWalker):
        '''
        :param reccipe: The data of the recipe. Starting from
            root / "minecraft:recipe_brewing"
        '''
        name = recipe / "description" / "identifier"
        if not name.exists or not isinstance(name.data, str):
            raise InvalidRecipeException("Recipe name is not a string")
        self.name = name.data

        input = recipe / "input"
        if not input.exists:
            raise InvalidRecipeException("Recipe 'input' property is missing")
        self.input = RecipeKey(input)

        reagent = recipe / "reagent"
        if not reagent.exists:
            raise InvalidRecipeException(
                "Recipe 'reagent' property is missing")
        self.reagent = RecipeKey(reagent)

        output = recipe / "output"
        if not output.exists:
            raise InvalidRecipeException("Recipe 'output' property is missing")
        self.output = RecipeKey(output)

Recipe = Union[RecipeCrafting, RecipeFurnace, RecipeBrewing]

def load_recipe(recipe_path: Path) -> Recipe:
    '''
    Loads a recipe from a file.
    '''
    # Load the file
    walker = load_jsonc(recipe_path)

    # Get all possible types of recipes
    recipe_shaped_data = walker / "minecraft:recipe_shaped"
    recipe_shapeless_data = walker / "minecraft:recipe_shapeless"
    recipe_furnace_data = walker / "minecraft:recipe_furnace"
    recipe_brewing_data = walker / "minecraft:recipe_brewing_mix"

    # Return first valid recipe type there is
    if recipe_shaped_data.exists:
        return RecipeCrafting(recipe_shaped_data, 'shaped')
    elif recipe_shapeless_data.exists:
        return RecipeCrafting(recipe_shapeless_data, 'shapeless')
    elif recipe_furnace_data.exists:
        return RecipeFurnace(recipe_furnace_data)
    elif recipe_brewing_data.exists:
        return RecipeBrewing(recipe_brewing_data)
    else:
        raise InvalidRecipeException(
            "Unknown recipe type (only minecraft:recipe_shaped, "
            "minecraft:recipe_shapeless, minecraft:recipe_furnace and "
            "minecraft:recipe_brewing_mix are supported)")

