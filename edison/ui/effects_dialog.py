"""Effects pop-up (CDC "Pop-up effets"), sprint S5.

Expected behaviour (CDC):
    * opened by the "Effet" tool or by the "Effet" entry of the right click menu of a clip;
    * shows the effects of the kind of the clip (``effects_of(VIDEO)`` / ``effects_of(AUDIO)``);
    * when an effect is selected: its settings are shown, the render area shows a PREVIEW,
      and the "Annuler" / "Appliquer" buttons appear.

Suggested design:
    * left: a ``QListWidget`` of the effects; right: one control per ``Param`` of the selected
      effect, generated automatically (``edison.ui.widgets.Slider`` for a number,
      ``edison.ui.widgets.ComboBox`` when ``param.choices`` is set);
    * preview: apply the effect to a COPY of the project (``copy.deepcopy``) and give this copy
      to the player (add a ``Player.set_preview(project_or_None)`` method); the real project
      only changes on "Appliquer", through ``controller.add_effect(...)`` (undoable);
    * "Annuler" or closing the window: ``player.set_preview(None)``.
"""

from PySide6.QtWidgets import QDialog


class EffectsDialog(QDialog):
    """Choose an effect and its settings, with a live preview.

    TODO(S5): build the interface described in the module docstring.
    """
