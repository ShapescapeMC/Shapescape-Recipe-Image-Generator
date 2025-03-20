(initial-setup)=
# Initial Setup

Before using the application, you need to configure a data repository where required assets are stored. This setup ensures that textures and mappings are accessible for generating recipe images.

(environment-variables)=
## Environment Variables
To define the repository, set the following environment variables:

- `SHAPESCAPE_RIG_DATABASE_URL` *(required)* – The Git URL of the {ref}`data repository<data-repository>` containing the resource pack, texture mappings, and other necessary files.
- `SHAPESCAPE_RIG_BRANCH` *(optional)* – The branch to use. Defaults to `main` if not specified.

If `SHAPESCAPE_RIG_DATABASE_URL` is not set, the application will exit with an error message prompting you to configure it.

```{warning}
The `SHAPESCAPE_RIG_DATABASE_URL` must use a format that Git can understand. For example, if your repository is hosted on GitHub at `https://github.com/ShapescapeMC/Shapescape-Recipe-Image-Generator-Data` the URL should be `https://github.com/ShapescapeMC/Shapescape-Recipe-Image-Generator-Data.git`. Note the `.git` extension at the end.
```


Need help setting an environment variable? See [this guide](https://www.howtogeek.com/787217/how-to-edit-environment-variables-on-windows-10-or-11/).
