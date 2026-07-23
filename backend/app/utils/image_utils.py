from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


def crop_image(input_path: str, output_path: str, x: int, y: int, width: int, height: int) -> None:
    with Image.open(input_path) as img:
        cropped = img.crop((x, y, x + width, y + height))
        cropped.save(output_path)


def rotate_image(input_path: str, output_path: str, degrees: int) -> None:
    with Image.open(input_path) as img:
        # PIL's rotate() is counter-clockwise; negate so the API matches
        # the clockwise convention used by rotate_video.
        rotated = img.rotate(-degrees, expand=True)
        rotated.save(output_path)


def flip_image(input_path: str, output_path: str, direction: str) -> None:
    with Image.open(input_path) as img:
        method = Image.FLIP_LEFT_RIGHT if direction == "horizontal" else Image.FLIP_TOP_BOTTOM
        result = img.transpose(method)
        result.save(output_path)


def resize_image(input_path: str, output_path: str, width: int, height: int) -> None:
    with Image.open(input_path) as img:
        resized = img.resize((width, height), Image.LANCZOS)
        resized.save(output_path)


def add_text_overlay_image(
    input_path: str,
    output_path: str,
    text: str,
    x: int,
    y: int,
    font_size: int = 32,
    color: str = "#FFFFFF",
    opacity: float = 1.0,
) -> None:
    with Image.open(input_path).convert("RGBA") as img:
        overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

        hex_color = color.lstrip("#")
        rgb = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4)) if len(hex_color) == 6 else (255, 255, 255)
        alpha = max(0, min(255, int(255 * opacity)))
        draw.text((x, y), text, font=font, fill=rgb + (alpha,))

        combined = Image.alpha_composite(img, overlay).convert("RGB")
        combined.save(output_path)


def denoise_image(input_path: str, output_path: str, strength: float = 10.0) -> None:
    import cv2

    img = cv2.imread(input_path)
    if img is None:
        raise ValueError(f"Could not read image at {input_path}")
    denoised = cv2.fastNlMeansDenoisingColored(img, None, strength, strength, 7, 21)
    cv2.imwrite(output_path, denoised)


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
        elif filter_name == "saturation":
            result = ImageEnhance.Color(img).enhance(intensity)
        elif filter_name == "sharpen":
            result = img.filter(ImageFilter.UnsharpMask(radius=2, percent=int(100 * intensity), threshold=3))
        else:
            raise ValueError(f"Unknown filter: {filter_name}")

        result.save(output_path)