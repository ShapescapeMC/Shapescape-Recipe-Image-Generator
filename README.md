# Recipe image generator
This is a simple program that generates the customizable images for recipe
books, based on the recipe files. The documentation is available
[here](/docs/README.md).

## Features
- generating images of shaped, shapeless and furnace recipes
- scaling the size of the image
- customizing the content of the images based on templates
- text based on the recipes
- counters in the text (useful for numering pages)
- the generator finds the textures of the items in the recipe based on the
  default and custom resource pack. The textures from custom resource pack
  override the textures from the default resource pack. If the packs don't
  provide enough information about the item to get the texture, the generator
  asks the user to provide it using a file chooser. The answers of the user
  are automatically uploaded to github so that the generator will never ask
  the same question again.

## Limitations
- the types of recipes not mentioned above are not supported
- the recipes that use multiple items in the same slot don't show the the
  number
- the applicaiton does not make its own renders of the the blocks, however it
  has a data folder with the renders of all of the blocks in the game using
  vanilla textures. See the
  ["Directories used by the tool"](#directories-used-by-the-tool)
  section below.
