from PIL import Image, ImageEnhance, ImageFilter, ImageOps


def crop_image(input_path: str, output_path: str, x: int, y: int, width: int, height: int) -> None:
    with Image.open(input_path) as img:
        cropped = img.crop((x, y, x + width, y + height))
        cropped.save(output_path)


def apply_filter(input_path: str, output_path: str, filter_name: str, intensity: float = 1.0) -> None:
    with Image.open(input_path) as img:
        img = img.convert("RGB")

        if filter_name == "grayscale":
            result = ImageOps.grayscale(img).convert("RGB")
        elif filter_name == "brightness":
            result = ImageEnhance.Brightness(img).enhance(intensity)
        elif filter_name == "contrast":
            result = ImageEnhance.Contrast(img).enhance(intensity)
        elif filter_name == "blur":
            result = img.filter(ImageFilter.GaussianBlur(radius=intensity * 2))
        elif filter_name == "sepia":
            grayscale = ImageOps.grayscale(img)
            result = ImageOps.colorize(grayscale, black="#3a2b1f", white="#d9c7a3")
        else:
            raise ValueError(f"Unknown filter: {filter_name}")

        result.save(output_path)
