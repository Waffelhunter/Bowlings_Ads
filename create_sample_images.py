#!/usr/bin/env python3
from PIL import Image, ImageDraw, ImageFont
import os


def create_sample_image(
    filename, text, size=(640, 480), bg_color=(255, 255, 255), text_color=(0, 0, 0)
):
    """Create a sample image with text"""
    # Create a new image with a white background
    image = Image.new("RGB", size, bg_color)
    draw = ImageDraw.Draw(image)

    # Draw the text in the center
    draw.text((size[0] // 2 - 50, size[1] // 2 - 30), text, fill=text_color)

    # Save the image
    image.save(filename)
    print(f"Created sample image: {filename}")


def main():
    # Create ads directory if it doesn't exist
    ads_dir = "ads"
    os.makedirs(ads_dir, exist_ok=True)

    # Create sample ads
    for i in range(1, 4):
        create_sample_image(
            os.path.join(ads_dir, f"ad{i}.jpg"),
            f"Sample Ad {i}",
            bg_color=(200, 200, 255) if i % 2 == 0 else (255, 200, 200),
        )

    print("Sample images created successfully!")


if __name__ == "__main__":
    main()
