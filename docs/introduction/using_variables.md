(using-variables)=
# Using variables
There are 3 kinds of variables that you can use in templates:
- last_recipe
- var
- counter

## last_recipe
The `last_recipe` variables lets you reference a property based on the last recipe that was used to generate the image. You can read more about defining the recipe properties {ref}`here<recipe-properties>`.

The syntax for referencing the `last_recipe` variable is `$last_recipe.<variable_name>` or `${last_recipe.<variable name>}`.

For example: `"DESCRIPTION: $last_recipe.description"` would be replaced with "DESCRIPTION:" and then the value of the `description` variable from the recipe_properties.json file.

## var
The `var` variables are only available when you're using a {ref}`Book Template<book-templates>` with a reference to a page. In the book template you can use the "scope" property to define custom variables. These variables will be available in the page template using the `var` variable. The `var` variables are designed to be used in the page templates to override parts of the book like the QR code of the map or the introduction text. etc. 

The syntax for referencing the `var` variable is `$var.<variable_name>` or `${var.<variable name>}`.

You can read more about the Book and Page Templates in the {ref}`Templates<templates>` article.

### Example:
The book template
```json
{
    "pages": {
        {
            "page": "Book description",
            "scope": {
                "text": "This is an example text."
            }
        }
    }
}
```

An example text component in the "Book description" page:
```json
// ...
    {
        "item_type": "$var.text",
        "text": "Example",
        "offset": [25, 15]
    },
// ...
```

## counter

The counter variables are used to generate a sequence of numbers.

The syntax for referencing the `counter` variable is `$counter.<counter_name>` or `${counter.<counter name>}`. Additionally, you can specify the starting value of the counter by adding `:<start>` to the end of the counter name. For example: `$counter.page_number:5` or `${counter.page_number:5}` would start the counter with 5. You can also specify an offset value by adding `:<+-offset>` after the end of the start value. The offset value is added to the counter after its incrementation. This is not only visual but also affects the value of the counter.

### Examples:
The counters always add 1 to the value. This means that if you want to keep the counter value unchanged you should set offset to -1.

- `$counter.page_number:5:-2` - counter that starts with 5, and when reached again removes 1 from the incremented value.
- `${counter.page_number:5:+3}` - counter that starts with 5, and when reached again adds 4 to the incremented value.
- `${counter.page_number:5:3}` - same as above but with simplified syntax.

By default the offset value is 0. This means that `$counter.page_number:5` and `$counter.page_number:5:0` are equivalent.


