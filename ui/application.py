"""Streamlit application composition boundary.

UI extraction is intentionally staged: the proven application is delegated to
the legacy implementation first, then individual screens can be moved without
changing runtime behavior.
"""

def run() -> None:
    # Import lazily so importing the package does not initialize Streamlit or
    # external services. Running legacy.app executes the existing Streamlit app.
    import runpy
    runpy.run_path(__file__.replace("ui/application.py", "legacy/app.py"), run_name="__main__")
