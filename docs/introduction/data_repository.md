(data-repository)=
# Data Repository

The data repository contains essential assets for the application, including item textures for generating recipe images. The repository you specify must be accessible via Git for both reading and writing.

```{note}
You can find an example, valid data repository at [https://github.com/ShapescapeMC/Shapescape-Recipe-Image-Generator-Data](https://github.com/ShapescapeMC/Shapescape-Recipe-Image-Generator-Data). If you configure the application to use it, it will partially work, however it doesn't contain all of the necessary assets like `block-images` and `RP`, and you will need to add them to your local files manually.
```

## How It Works
- When the application starts, it automatically pulls the latest changes from the repository.
- If the application encounters an unknown item texture, it prompts you for the correct path and updates the repository automatically.
- This setup is especially useful for teams: once a texture path is provided, others won’t need to define it again.
- The generator saves the repository in your user files in: `%userprofile%/AppData/Local/Shapescape/recipe-image-generator/data`.

(data-repository-structure)=
## Data Repository Structure
The structure of the data repository is the same as the {ref}`project structure<project-structure>`. But it has some additional folders.

For simplicity, this section only describes the differences between the project structure and the data repository structure. The items written in bold are unique to the data repository and don't have matching items in the project directory.


📁 block-images\
📁 **example-workspace**\
📁 fonts\
📁 images\
📁 **RP**\
📁 templates\
🗒️ data_map.json\

### 📁 RP
This path should contain a resource pack (typically vanilla, but can be customized) used for generating images. When you're working in the interactive mode, pressing the "Vanilla RP" button opens this directory.

### 📁 example-workspace
This folder contains an example workspace. It's also used when you press the "Initialize" button to create a new project. The files from this folder are copied to the working directory during the initialization. See {ref}`Project Structure<project-structure>` for details.

