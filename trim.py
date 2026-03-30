import sys
from PIL import Image

def trim_transparent(image_path, output_path):
    print(f"Trimming {image_path}...")
    try:
        im = Image.open(image_path).convert("RGBA")
        bbox = im.getbbox()
        if bbox:
            print(f"Found bounding box: {bbox}")
            # Crop the image to the bounding box
            im_cropped = im.crop(bbox)
            im_cropped.save(output_path, "PNG")
            print(f"Cropped image saved to {output_path}")
        else:
            print("Image is entirely transparent or bounding box not found.")
    except Exception as e:
        print(f"Error processing image: {e}")

trim_transparent("public/brand/coentax-logo-transparent.png", "public/brand/coentax-logo-transparent.png")
