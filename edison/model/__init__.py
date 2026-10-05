"""Data model of a project and editing operations.

Rule of the architecture (CDC "Architecture"): nothing in this package imports Qt.
The model can then be unit tested, copied to worker threads and saved as JSON.
"""
