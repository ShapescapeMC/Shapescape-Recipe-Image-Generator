(recipe-properties)=
# Recipe Properties
## The recipe_properties.json file

The recipe properties is a JSON file that is used to provide custom data to be rendered on the recipe images. The file is structured as a JSON object where the keys are the recipe IDs and the values are objects that contain the data for the recipe. The `recipe_properties.json` file is located in the root of the working directory.

The code below shows an example *recipe_properties.json* file:
```json
{
	"shapescape:diving_gear": {
		"description": ["A diving gear that allows you to breathe underwater."],
		"name": ["Diving Gear"],
		"image": "image1"
	},
	"shapescape:top_hat": {
		"name": ["Top Hat"],
	},
}
```

The top level identifiers ("shapescape:diving_gear" and "shapescape:top_hat") are the IDs of the recipes (not to be confused with the IDs of the items).

In the example above, the recipe_properties.json file contains information two recipes. The first recipe provides 3 variables - *name*, *description* and *image*. The second image provides only the name variable.

Not every recipe needs to provide the same set of variables. You can name your variables however you want. The only important thing is that the templates that you're using get all the variables that they need.

The variables can be accessed in the template files using the `$last_recipe.<variable name>` syntax (for exaple `$last_recipe.name`). You can read more about using the variables of the last_recipe in the {ref}`Templates<templates>` article.