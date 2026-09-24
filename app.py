"""RoboMANTAP Streamlit entry point.

The first migration stage deliberately keeps the audited UI implementation
unchanged under legacy/app.py. This entry point is now the stable composition
boundary for the future UI module extraction.
"""
from ui.application import run

if __name__ == "__main__":
    run()
