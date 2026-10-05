"""Controllers: the link between the model (no Qt) and the views (Qt).

The views never change the model themselves: they call a method of
``ProjectController`` (or ``Player``) and refresh when its signals are emitted.
"""
