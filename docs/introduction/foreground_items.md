(foreground-items)=
# Foreground items
This section describes all kinds of the "foreground" items that you can put into your templates. The foreground items are the objects that define the images pasted on top of the background of the image. They are the building blocks of the templates.

You can learn more about the structure of the template files in the {ref}`Templates<templates>` article.

Syntax:
```json
{
    "item_type": "image",
    // The rest of the properties depend on the type of the foreground item
}
```
Every foreground item has the "item_type" property. This property defines what kind of item it is. The specific types of the foreground items are described below.

## Image Foreground Item
The purpose of the `image` foreground item is to paste an image on top of the background image. You can use the `image` items to compose more complex images from smaller images.

Syntax:
```json
{
    "item_type": "image",
    "image": "example_image.png",
    "offset": [165, 230],
    "size": [70, 70]
}
```
### image
The `image` property defines the path to the image file. The path is relative to the *images* folder (either the *images* of the project or from the {ref}`data repository<data-repository>`).

The image property can use variables. You can read more about the variables in the {ref}`Using variables<using-variables>` article.

### offset
The offset property defines where to paste the image. It's a vector of the UV coordinates (in pixels) of the base image starting from the top left corner.

### size
This property defines the size of the image. It's optional and if it's not provided, the size of the pasted image will be the same as the size of the original image.

If the source image has a different aspect ratio than the ratio defined in the `size` property, it will be resized to fit inside the bounding box defined by the `size` and `offset` properties without stretching it.

## Text Foreground Item
The text foreground item is used to add text to your generated images.

Syntax:
```json
{
    "item_type": "text",
    "text": "Example",
    "offset": [25, 15],
    "scale": 20,
    "color": [148, 116, 90, 255],
    "font": "plexi 1.2.ttf",
    "spacing": 1.0,
    "anti_alias": false,
    "line_length": 80,
    "alignment": "left",
    "anchor": "la"
}
```

Note that a lot of the `text` foreground item properties are optional and you can omit them to use the default values.

### text
The `text` property defines the content of the text to be added to the image. It can be a string or a list of strings. If the text is a list, the items of that list will be separated with new lines.

The text property can use variables. You can read more about the variables in the {ref}`Using variables<using-variables>` article.

### offset
The offset property defines where to paste the image. It's a vector of the UV coordinates (in pixels) of the base image starting from the top left corner.

### scale
The scale property defines the size of the font. The default value is 12.

### color
The `color` the color of the text in RGBA fromat. The default value is white [255, 255, 255, 255].

### font
This is the path to the font file relative to the *fonts* folder.

### spacing
Spacing defines the amount of space between the lines. The default value is `1.0`. It accepts any float value.

### anti_alias
It defines if the text should be anti-aliased. The default value is `false`.
### line_length
Line length is an optional property that limits the number of characters in a line. By default it's undefined and the layout manager doesn't do any wrapping on it's own.
### alignment
Defines text alignment. The default value is "left". The accepted values are "left:, "right" and "center".

### anchor
The anchor property is an advanced feature that defines the anchor type of the text. The value of this property is passed directly to the Python's Pillow library.

You can read more about the text-anchors in the Pillow documentation:
- https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html

The default anchor is "la" (left-ascender), this is the most common value.

If you need to center the text, you can use the "ma" (middle-ascender) anchor. The

The difference between the `alignment` and `anchor` is that the alignment defines the alignemnt of the lines of multi-line text in relation to one another while the anchor defines the position of the text box.

## Recipe Shaped Foreground Item
The `recipe_shaped` foreground item is used to add a **shaped or shapeless** crafting recipe to the image. It adds any recipe that can be crafted in the crafting table.

```json
{
    "item_type": "recipe_shaped",
    "background": "crafting_full_background.png",
    "offset": [25, 107],
    "recipe_pattern": ".+",
    "items": {
        "0,0": {"size": [16, 16], "offset": [2, 2]},
        "1,0": {"size": [16, 16], "offset": [2, 20]},
        "2,0": {"size": [16, 16], "offset": [2, 38]},
        "0,1": {"size": [16, 16], "offset": [20, 2]},
        "1,1": {"size": [16, 16], "offset": [20, 20]},
        "2,1": {"size": [16, 16], "offset": [20, 38]},
        "0,2": {"size": [16, 16], "offset": [38, 2]},
        "1,2": {"size": [16, 16], "offset": [38, 20]},
        "2,2": {"size": [16, 16], "offset": [38, 38]},
        "result": {"size": [16, 16], "offset":[96, 21]}
    }
}
```
### background
The background image of the recipe works like the main background. It defines the size of the recipe image unless you
provide the `size` property. The recipe images can also be scaled using the `scale` property.

### offset
The offset property defines where to paste the image. It's a vector of the UV coordinates (in pixels) of the base image starting from the top left corner.

### recipe_pattern
The `recipe_pattern` property is a regex pattern matched against recipe identifiers to determine if they're suitable for this foreground item.

You can read about the regular expresssions here:
- https://en.wikipedia.org/wiki/Regular_expression

For basic usage, you can use the `.+` pattern which matches any recipe. If you want to match only specific recipe names you can list them and separate them with a pipe `|` character. For example, if you want to match only the `minecraft:stone` and `minecraft:stone_slab` recipes, you can use the following pattern: `minecraft:stone|minecraft:stone_slab`.

### items

The `items` dictionary that define the position and size of the items. All of the keys are optional. For example you can define a recipe_shaped object that only shows the result item or only the input items.

The keys with the numbers define the items in the crafting grid where `"0,0"` is the top left corner and `"2,2"` is the bottom right corner. The `"result"` key defines the position of the result item.

## Recipe Furnace Foreground Item
The `recipe_furnace` foreground item is used to add a **furnace** recipe to the generated image.

```json
{
    "background": "furnace_full_background.png",
    "item_type": "recipe_furnace",
    "offset": [25, 178],
    "recipe_pattern": ".+",
    "items": {
        "input": {"size": [16, 16], "offset":[20, 2]},
        "output": {"size": [16, 16], "offset":[96, 21]}
    }
}
```
Furnace recipe uses the same properties as the `recipe_shaped` except that the "items" dictionary has a "input" and "output" keys.

## Recipe Brewing Foreground Item
The `recipe_brewing` foreground item is used to add a **brewing** recipe to the generated image.
```json
{
    "background": "brewing_full_background.png",
  "item_type": "recipe_brewing",
  "offset": [0, 0],
  "recipe_pattern": ".+",
  "items": {
      "reagent": {"size": [16, 16], "offset": [53, 3]},
      "input": {"size": [16, 16], "offset": [53, 37]},
      "output": {"size": [16, 16], "offset": [100, 20]}
  }
}
```
Brewing recipe uses the same properties as the `recipe_shaped` except that the "items" dictionary has a "reagent", "input" and "output" keys.

## Recipe Any Foreground Item

Recipe any is a combination of all of the other recipe types. This foreground item requires 3 separate recipe types to be defined in it to cover all the possible cases - shaped, brewing and furnace.

```json
{
    "item_type": "recipe_any",
    "recipe_pattern": ".+",
    "recipe_shaped": {
        "background": "crafting_full_background.png",
        "offset": [25, 249],
        "items": {
            "0,0": {"size": [16, 16], "offset": [2, 2]},
            "1,0": {"size": [16, 16], "offset": [2, 20]},
            "2,0": {"size": [16, 16], "offset": [2, 38]},
            "0,1": {"size": [16, 16], "offset": [20, 2]},
            "1,1": {"size": [16, 16], "offset": [20, 20]},
            "2,1": {"size": [16, 16], "offset": [20, 38]},
            "0,2": {"size": [16, 16], "offset": [38, 2]},
            "1,2": {"size": [16, 16], "offset": [38, 20]},
            "2,2": {"size": [16, 16], "offset": [38, 38]},
            "result": {"size": [16, 16], "offset":[96, 21]}
        }
    },
    "recipe_furnace": {
        "background": "furnace_full_background.png",
        "offset": [0, 0],
        "items": {
            "input": {"size": [16, 16], "offset":[20, 2]},
            "output": {"size": [16, 16], "offset":[96, 21]}
        }
    },
    "recipe_brewing": {
      "background": "brewing_full_background.png",
      "offset": [0, 0],
      "items": {
        "reagent": {"size": [16, 16], "offset": [53, 3]},
        "input": {"size": [16, 16], "offset": [53, 37]},
        "output": {"size": [16, 16], "offset": [100, 20]}
      }
    }
}
```

### recipe_shaped
The `recipe_shaped` property is a dictionary that defines the properties of the shaped recipe. It uses the same properties as the `recipe_shaped` foreground item.

The only exception is that the `recipe_pattern` property is on the outer level of the `recipe_any` item.

### recipe_furnace
The `recipe_furnace` property is a dictionary that defines the properties of the furnace recipe. It uses the same properties as the `recipe_furnace` foreground item.

The only exception is that the `recipe_pattern` property is on the outer level of the `recipe_any` item.

### recipe_brewing
The `recipe_brewing` property is a dictionary that defines the properties of the brewing recipe. It uses the same properties as the `recipe_brewing` foreground item.

The only exception is that the `recipe_pattern` property is on the outer level of the `recipe_any` item.
