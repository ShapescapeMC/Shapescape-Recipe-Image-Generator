<img src="./header.jpg" alt="Header only used for decoration" style="width:100%" loading="lazy">


# Recipe Image Generator
This is a simple program that generates the customizable images for recipe books, based on the recipe files.

## Features
- generating images of shaped, shapeless and furnace recipes
- scaling the size of the image
- customizing the content of the images based on templates
- text based on the recipes
- counters in the text (useful for numering pages)
- the generator finds the textures of the items in the recipe based on the default and custom resource pack. The textures from custom resource pack override the textures from the default resource pack. If the packs don't provide enough information about the item to get the texture, the generator asks the user to provide it using a file chooser. The answers of the user are automatically uploaded to GitHub so that the generator will never ask the same question again.

## Limitations
- the types of recipes not mentioned above are not supported
- the recipes that use multiple items in the same slot don't show the the number
- the application does not make its own renders of the blocks, however it has a data folder with the renders of all of the blocks in the game using vanilla textures.

## 📒 Documentation
Documentation for the filter is available here: https://shapescape-recipe-image-generator.readthedocs.io/en/latest/

You can find the documentation for all filters and tools on our organisation page https://github.com/ShapescapeMC.

## 👷 Contributing
We welcome contributions from the community! If you'd like to contribute to this project, please read our [contribute file](https://github.com/ShapescapeMC/Shapescape-Recipe-Image-Generator/blob/main/CONTRIBUTING.md) for guidelines on how to get started.

## 🗒️ License
This project is licensed under the GNU v.3.0 License - see the [LICENSE](https://github.com/ShapescapeMC/Shapescape-Recipe-Image-Generator?tab=GPL-3.0-1-ov-file) file for details.

This license ensures that the tool remains open source, while still allowing you to use the generated content in your commercial Minecraft projects.

## 📧 Contact
For questions, suggestions, or support, please reach out via mail to [contact@shapescape.com](mailto:contact@shapescape.com)
