"""PyInstaller entry point; all worker modes dispatch explicitly in ros.desktop."""
from ros.desktop import main
raise SystemExit(main())
