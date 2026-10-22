"""Project form paths, save, adoption, and rename.

This package root stays empty on import. The code generator imports
``project.forms`` while it is still loading, and save imports the generator.
Importing save, create, or rename from here would cycle. Import the module
you need.
"""
