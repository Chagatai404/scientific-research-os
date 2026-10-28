"""Focused integration checks in disposable storage. No live provider or personal vault access."""
from pathlib import Path
import os
import sys
import unittest

root=Path(__file__).resolve().parents[1]; os.chdir(root); sys.path.insert(0,str(root)); sys.path.insert(0,str(root/'tests'))
temp=root/'.desktop-fixtures'/'tmp';temp.mkdir(parents=True,exist_ok=True)
os.environ.update(ROS_NO_VAULT='1',ROS_HOME=str(root/'.desktop-fixtures'/'contracts'),TEMP=str(temp),TMP=str(temp),PYTHONUTF8='1')
suite=unittest.TestSuite()
for pattern in ('test_ros_desktop.py','test_ros_serve.py','test_ros_operations.py','test_ros_provider_protocols.py','test_ros_pedagogy.py','test_notebook_*.py','test_architecture.py'):
    suite.addTests(unittest.defaultTestLoader.discover(str(root/'tests'),pattern=pattern))
result=unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
