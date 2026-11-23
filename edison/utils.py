"""Small helpers shared by the whole application (no Qt dependency)."""


def format_time(seconds: float, precise: bool = True) -> str:
    """Format a duration as ``mm:ss`` or ``mm:ss.cc``.

    Parameters
    ----------
    seconds : float
        Duration in seconds.
    precise : bool
        Add hundredths of a second.

    Returns
    -------
    str
        Formatted time, with hours only when needed (``h:mm:ss``).
    """
    hundredths = int(round(max(0.0, seconds) * 100))
    total_seconds, hundredths = divmod(hundredths, 100)
    minutes, secs = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    text = f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"
    return f"{text}.{hundredths:02d}" if precise else text


def format_size(size: float) -> str:
    """Format a number of bytes in French units (Ko, Mo, Go).

    Parameters
    ----------
    size : float
        Size in bytes.

    Returns
    -------
    str
        Human readable size, e.g. ``"12,5 Mo"``.
    """
    for unit in ("octets", "Ko", "Mo"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "octets" else f"{size:.1f} {unit}".replace(".", ",")
        size /= 1024
    return f"{size:.2f} Go".replace(".", ",")


def fit_size(width: int, height: int, max_width: int, max_height: int) -> tuple[int, int]:
    """Scale ``width x height`` to fit in a box while keeping the aspect ratio.

    Parameters
    ----------
    width, height : int
        Source size.
    max_width, max_height : int
        Box size.

    Returns
    -------
    tuple of int
        Fitted size, rounded to even numbers (required by video encoders).
    """
    if width <= 0 or height <= 0:
        return max_width - max_width % 2, max_height - max_height % 2
    scale = min(max_width / width, max_height / height)
    fitted_width = max(2, int(round(width * scale / 2)) * 2)
    fitted_height = max(2, int(round(height * scale / 2)) * 2)
    return min(fitted_width, max_width), min(fitted_height, max_height)
