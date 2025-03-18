'''
This module implements various image processing functions.
'''
from typing import (
    Callable, NamedTuple, Optional, Tuple, Literal, List, Dict, Any)
import logging
from pathlib import Path
from PIL import Image, ImageFont, ImageDraw, ImageChops
import numpy as np
from .utils import TextureNotFound

AlignX = Literal["left", "middle", "right"]
AlignY = Literal["top", "middle", "bottom"]

OptPath = Optional[Path]


def padding_thumbnail(
        image: Image.Image, width: int, height: int,
        align_x: AlignX = "middle", align_y: AlignY = "middle",
        background_color: Tuple[int, int, int, int] = (0, 0, 0, 0)
) -> Image.Image:
    '''
    Works similar to PIL.Image.thumbnail, but adds padding to the image. The
    original image is scaled to fit the given width and height. If it has
    different aspect ratio than the given width and height, the image fully
    fills one of the dimensions and the othe one is padded with the background
    color. The aligments specify where the image is placed in the padded
    image.

    :param image: the image to be scaled and padded.
    :param width: Desired width of the padded image.
    :param height: Desired height of the padded image.
    :param align_x: X Alignment of the image in the padded image.
    :param align_y: Y Alignment of the image in the padded image.
    :param background_color: Background color of the padded area.
    '''
    if image.width < width or image.height < height:
        ratio = max(width/image.width, height/image.height)
        upscaled_width = int(image.width * ratio)
        upscaled_height = int(image.height * ratio)
        image = image.resize(
            (upscaled_width, upscaled_height),
            Image.NEAREST)
    image.thumbnail((width, height), Image.NEAREST)
    image_with_padding = Image.new(
        "RGBA", (width, height), background_color)
    # X alignment
    if align_x == "left":
        x_offset = 0
    elif align_x == "middle":
        x_offset = (width - image.width) // 2
    elif align_x == "right":
        x_offset = width - image.width
    else:
        raise Exception("Invalid align_x")
    # Y alignment
    if align_y == "top":
        y_offset = 0
    elif align_y == "middle":
        y_offset = (height - image.height) // 2
    elif align_y == "bottom":
        y_offset = height - image.height
    else:
        raise Exception("Invalid align_y")
    image = image.convert("RGBA")
    image_with_padding.alpha_composite(image, (x_offset, y_offset))
    return image_with_padding

class Subimage(NamedTuple):
    '''
    Subimage is a class that contains the data for pasting an image into
    another image.
    '''
    x: int  # x position in the image
    y: int  # y position in the image
    scale: float  # scale factor
    image_provider: Callable[[], Image.Image]  # function that returns images
    # Optional properties to be bassed if padding_thumbnail function is used
    padding_thumbnail_properties: Optional[Dict[str, Any]] = None

    # Whether to replace alpha values with true/false values (> 0 --> True;
    # == 0 --> False)
    alpha_clip: bool = False


class SubimageText(NamedTuple):
    '''
    SubimageText represents a text that should be pasted on an image.
    '''
    text: str
    x: int
    y: int
    scale: float  # The font size
    font: str  # The font name
    color: Tuple[int, int, int, int]  # RGBA
    alignment: Literal["left", "right", "center"]  # The text alignment
    spacing: float  # The spacing between the lines
    anti_alias: bool  # Whether to use anti-aliasing
    # Text anchor (see https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html)
    anchor: str


def get_custom_image(
        *, image_size: Optional[Tuple[int, int]], scale: float,
        background: OptPath, subimages: List[Subimage]) -> Image.Image:
    '''
    Returns any custom image of given size, with the given background and
    subimages pasted on top of it.

    :param image_size: the size of the image when the background is not None
        this property is optional as the function is able to get the with
        from the background image.
    :param scale: the scale factor for the image.
    :param background: the optional background of the image. If the background
        doesn't match the image size it will be resized to fit using the
        padding_thumbnail function.
    :param subimages: the list of the images to paste on image.
    '''
    if image_size is None and background is None:
        raise ValueError(
            "You must provide either size of the image or the "
            "background (or both)")
    if image_size is not None:
        image_width, image_height = image_size
    else:
        with Image.open(background) as img:
            image_width, image_height = img.width, img.height
    transparent = (0, 0, 0, 0)
    base_image = Image.new(
        "RGBA", (int(image_width*scale), int(image_height*scale)),
        color=transparent)
    if background is not None:
        if not background.exists():
            raise TextureNotFound(
                f"File not found: {background.as_posix()}")
        with Image.open(background) as img:
            background_image = padding_thumbnail(
                img, int(image_width*scale), int(image_height*scale),
                background_color=transparent)
        paste_that_works(base_image, background_image, (0, 0))
    for subimage in subimages:
        paste_subimage(base_image, scale, subimage)
    return base_image


def paste_subimage(image: Image.Image, scale: float, subimage: Subimage):
    '''
    paste_subimage pastes subimage on top of the image. The scale is the scale
    value of the original image. It affects the paste coordinates and the size
    of the pasted image.

    :param image: the base image
    :param scale: the scale of the main image (the coordinates provided in
        the subimage are scaled with this value)
    :param subimage: the properties of the subimage
    '''
    if subimage.padding_thumbnail_properties is not None:
        # Modify the padding_thumbnail_properties so it will return the
        # resized image
        w = subimage.padding_thumbnail_properties["width"]
        h = subimage.padding_thumbnail_properties["height"]
        w = w*subimage.scale*scale
        h = h*subimage.scale*scale
        subimage.padding_thumbnail_properties["width"] = w
        subimage.padding_thumbnail_properties["height"] = h
        subimg = padding_thumbnail(
            subimage.image_provider(), **subimage.padding_thumbnail_properties)
    else:
        subimg = subimage.image_provider()
        size = (
            int(subimg.width*subimage.scale*scale),
            int(subimg.height*subimage.scale*scale))
        subimg = subimg.resize(size, Image.NEAREST)
    if subimage.alpha_clip:
        subimg = subimg.convert("RGBA")
        data = np.array(subimg)
        data[..., 3] = (data[..., 3] > 0) * 255
        subimg = Image.fromarray(data)
    pos = (int(subimage.x*scale), int(subimage.y*scale))
    paste_that_works(image, subimg, pos)


def paste_that_works(
        background: Image.Image, overlay: Image.Image, pos: tuple[int, int]):
    '''
    This function defines what Image.paste() should do.
    '''
    overlay = overlay.convert("RGBA")

    # We use overlay_img to get the max alpha value from the image and
    # subimg because image.paste() doen't copy the alpha channel correctly

    # Create overlay image with subimg pasted on it
    overlay_img = Image.new("RGBA", background.size, (0, 0, 0, 0))
    overlay_img.paste(overlay, pos)

    # Get max alpha value from the image and overlay_img
    overlay_arr = np.array(overlay_img)
    background_arr = np.array(background)
    # image_arr[..., 3] = np.maximum(image_arr[..., 3], overlay_arr[..., 3])

    # Convert to float for easier calculations
    background_arr = background_arr.astype(np.float32) / 255
    overlay_arr = overlay_arr.astype(np.float32) / 255

    background_rgb = background_arr[..., :3]
    overlay_rgb = overlay_arr[..., :3]
    background_a = background_arr[..., 3:4]
    overlay_a = overlay_arr[..., 3:4]

    # Calculate the final image
    final_img = np.zeros_like(background_arr)
    # Alpha channel is a clamped (0, 1) sum of the overlay_array and image_array
    final_img[..., 3:4] = np.minimum(overlay_a + background_a, 1)

    # Colors:
    # (1) RGB channels of the overlay behave like color filters:
    # - for alpha 0.5 the correct operation would be: fnal_img*overlay_arr,
    # - for alpha 1 it would be: overlay_img
    # - for alpha 0 it would be: background_rgb
    # This would suggest that the color formula is:
    # (overlay_rgb * overlay_a) + (background_rgb * (1 - overlay_a))
    # (2) Unfortunately this doesn't work if the background is not fully opaque
    # because the background it means that the background color could be used
    # in the final image even if it's invisible.
    # (3) The 'ratio' variable solves the problem. It represents how muc color
    # from the overlay should be used to get the final image. '1-ratio' is the
    # amount of the color from the background that should be used.
    ratio = (
        overlay_a +
        (1.0 - overlay_a) * (1.0 - background_a) * overlay_a
    )
    # Explanation:
    # LEFT SIDE:
    # - 'overlay_a' - the base alpha value of the overlay
    # RIGHT SIDE:
    # - '+ (1.0 - overlay_a)' - the remaining alpha value.
    # - '* (1.0 - background_a)' - creates a dependency "the more transparent
    #   the background is, the more of the overlay color is used"
    # - '* overlay_a' scales the value by overlay_a to create a dependency "the
    #   more transparent the overlay is, the more of the background color is"
    final_img[..., :3] = (
        overlay_rgb * ratio +
        background_rgb * (1.0 - ratio)
    )

    # Convert back to 8-bit
    final_img_arr = np.ceil(final_img * 255).astype(np.uint8)
    final_img = Image.fromarray(final_img_arr, mode="RGBA")

    # Paste new pixels on the image (this completely overrides current 'image')
    background.paste(final_img, (0, 0))

def paste_subimagetext(
        image: Image.Image, scale: float, subimage_text: SubimageText):
    '''
    Adds text to image.

    :param image: the base image
    :param scale: the scale of the base image (affects where the text is pased
        and its scale)
    :param subimage_text: the text to paste
    '''
    font = ImageFont.truetype(
        font=subimage_text.font, size=int(subimage_text.scale*scale))
    draw = ImageDraw.Draw(image)
    pos = (int(subimage_text.x*scale), int(subimage_text.y*scale))
    true_spacing = subimage_text.spacing*scale

    # Disable antialiasing
    # https://stackoverflow.com/a/62813181
    # https://pillow.readthedocs.io/en/stable/handbook/concepts.html#concept-modes
    if not subimage_text.anti_alias:
        draw.fontmode = "1"
    draw.text(
        pos, subimage_text.text, font=font, fill=subimage_text.color,
        spacing=true_spacing, align=subimage_text.alignment,
        anchor=subimage_text.anchor)
