"""Lazy compatibility facade for historical character-card service imports."""

__all__ = [
    "export_character_cards", "import_character_card", "list_character_cards",
    "save_character_card", "update_character_card",
]


def list_character_cards(*args, **kwargs):
    from src.webui.services.character_cards import list_character_cards as implementation
    return implementation(*args, **kwargs)


def save_character_card(*args, **kwargs):
    from src.webui.services.character_cards import save_character_card as implementation
    return implementation(*args, **kwargs)


def update_character_card(*args, **kwargs):
    from src.webui.services.character_cards import update_character_card as implementation
    return implementation(*args, **kwargs)


def export_character_cards(*args, **kwargs):
    from src.webui.services.character_cards import export_character_cards as implementation
    return implementation(*args, **kwargs)


async def import_character_card(*args, **kwargs):
    from src.webui.services.character_cards import import_character_card as implementation
    return await implementation(*args, **kwargs)
