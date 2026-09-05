project = "swissco"
author = "Prospex"
copyright = "2026 Prospex"
release = "0.3.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx_copybutton",
]

autodoc_member_order = "bysource"
autodoc_typehints = "description"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

html_theme = "furo"
html_title = "swissco"

html_theme_options = {
    "source_repository": "https://github.com/prospex-ch/swissco-cli",
    "source_branch": "master",
    "source_directory": "docs/",
}
